import os
import traceback
import logging
import datetime
import threading
import time
import requests
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 環境変数とサービス初期化
load_dotenv()
SERVICE_ACCOUNT_FILE = 'aiko-bot-log-xxxxx.json'
SPREADSHEET_ID1 = os.getenv("SPREADSHEET_ID1")  # 会話ログ
SPREADSHEET_ID2 = os.getenv("SPREADSHEET_ID2")  # 従業員情報
SPREADSHEET_ID3 = os.getenv("SPREADSHEET_ID3")  # 顧客情報
SPREADSHEET_ID4 = os.getenv("SPREADSHEET_ID4")  # 会社情報
LOG_RANGE_NAME = '会話ログ!A:J'

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheet = build('sheets', 'v4', credentials=creds).spreadsheets()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- キャッシュ関連 ---
employee_data_cache = []
customer_data_cache = []
company_data_cache = []
global_chat_cache = []

# 各種キャッシュ更新処理
def refresh_cache(name, spreadsheet_id, range_str, target_cache, interval=300):
    def update_loop():
        global_vars = globals()
        while True:
            try:
                print(f"[愛子] {name}キャッシュ更新中...")
                result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_str).execute().get("values", [])
                global_vars[target_cache] = result
                print(f"[愛子] {name}キャッシュ完了：{len(result)-1}件")
            except Exception as e:
                print(f"[愛子] {name}キャッシュ失敗:", e)
            time.sleep(interval)
    threading.Thread(target=update_loop, daemon=True).start()

# Renderスリープ防止
def keep_server_awake(interval_seconds=900):
    def ping():
        while True:
            try:
                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
                print("[愛子] Render ping:", url)
                requests.get(url)
            except Exception as e:
                print("[愛子] ping失敗:", e)
            time.sleep(interval_seconds)
    threading.Thread(target=ping, daemon=True).start()

# --- データ保存・取得 ---
def save_conversation_log(user_id, user_name, speaker, message):
    ts = datetime.datetime.now().isoformat()
    values = [[ts, user_id, user_name, speaker, message, '', '', '', '', '']]
    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range=LOG_RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body={'values': values}
        ).execute()
    except Exception as e:
        logging.error("[愛子] ログ保存失敗:", e)

def delete_memory_entries(user_id, user_name, keyword):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID4, range='会社情報!A:Z').execute()
        rows = result.get("values", [])
        new_rows = [rows[0]] + [r for r in rows[1:] if user_id not in r or keyword not in ' '.join(r)]
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID4,
            range='会社情報!A:Z',
            valueInputOption='RAW',
            body={'values': new_rows}
        ).execute()
    except Exception as e:
        print("[愛子] 削除失敗:", e)

def load_recent_chat_history(user_name, limit=20):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range=LOG_RANGE_NAME).execute()
        rows = result.get("values", [])[1:]
        recent = [r for r in rows if len(r) >= 5 and r[2] == user_name][-limit:]
        return [{"role": "user" if r[3] == "user" else "assistant", "content": r[4]} for r in recent]
    except Exception as e:
        return []

def load_all_chat_history(max_messages=300):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range=LOG_RANGE_NAME).execute()
        rows = result.get("values", [])[1:]
        return [{"role": "user" if r[3] == "user" else "assistant", "content": r[4]} for r in rows[-max_messages:] if len(r) >= 5]
    except Exception as e:
        return []

# --- LINE処理 ---
@handler.add(FollowEvent)
def handle_follow(event):
    uid = event.source.user_id
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="愛子です。お友だち登録ありがとうございます。"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id
    msg = event.message.text
    user_name = uid  # ユーザー名取得の拡張可能

    # 自然言語削除処理
    if "削除して" in msg or "忘れて" in msg:
        kw = msg.replace("削除して", "").replace("忘れて", "").strip()
        delete_memory_entries(uid, user_name, kw)

    # 自動記憶処理（例：覚えておいて、子供の名前は、など）
    if "覚えておいて" in msg or "子供の名前" in msg or "ペットは" in msg:
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        new_row = [[
            "個人情報", "自由記述", msg, msg, "", "", now, user_name, "1", uid
        ]]
        try:
            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID4,
                range="会社情報!A:J",
                valueInputOption="USER_ENTERED",
                body={"values": new_row}
            ).execute()
        except Exception as e:
            print("[愛子] 記憶保存失敗:", e)

    # 会話履歴を取得
    personal_log = load_recent_chat_history(user_name)
    global_log = global_chat_cache[-30:]
    messages = [
        {"role": "system", "content": "あなたは社内秘書の愛子です。情報制限はありません。"},
        {"role": "user", "content": msg}
    ] + global_log + personal_log

    # OpenAI呼び出し
    response = client.chat.completions.create(model="gpt-4o", messages=messages)
    reply = response.choices[0].message.content.strip()

    save_conversation_log(uid, user_name, "user", msg)
    save_conversation_log(uid, user_name, "assistant", reply)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# プッシュ送信用API
@app.route("/push", methods=["POST"])
def push_message():
    data = request.get_json()
    uid = data.get("target_uid")
    msg = data.get("message")
    if not uid or not msg:
        return jsonify({"error": "Missing parameters"}), 400
    line_bot_api.push_message(uid, TextSendMessage(text=msg))
    return jsonify({"status": "success"}), 200

# Webhookエンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 初期処理
if __name__ == "__main__":
    refresh_cache("従業員情報", SPREADSHEET_ID2, '従業員情報!A:W', "employee_data_cache")
    refresh_cache("顧客情報", SPREADSHEET_ID3, '顧客情報!A:T', "customer_data_cache")
    refresh_cache("会社情報", SPREADSHEET_ID4, '会社情報!A:Z', "company_data_cache")
    global global_chat_cache
    global_chat_cache = load_all_chat_history()
    keep_server_awake()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
