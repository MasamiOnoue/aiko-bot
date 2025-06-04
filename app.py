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

# シート設定
EMPLOYEE_SHEET_RANGE = '従業員情報!A:W'
CUSTOMER_SHEET_RANGE = '顧客情報!A:T'
COMPANY_SHEET_RANGE = '会社情報!A:Z'
LOG_RANGE_NAME = '会話ログ!A:J'

# キャッシュ用変数
global_chat_cache = []
employee_data_cache = []

# Flask & LINE初期化
load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv("SPREADSHEET_ID1")
SPREADSHEET_ID2 = os.getenv("SPREADSHEET_ID2")
SPREADSHEET_ID3 = os.getenv("SPREADSHEET_ID3")
SPREADSHEET_ID4 = os.getenv("SPREADSHEET_ID4")

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# スリープ防止
def keep_server_awake(interval_seconds=900):
    def ping():
        while True:
            try:
                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
                requests.get(url)
            except Exception as e:
                print("[愛子] ping失敗:", e)
            time.sleep(interval_seconds)
    threading.Thread(target=ping, daemon=True).start()

# 従業員キャッシュ
def refresh_employee_data_cache(interval_seconds=300):
    def update_loop():
        global employee_data_cache
        while True:
            try:
                result = sheet.values().get(spreadsheetId=SPREADSHEET_ID2, range=EMPLOYEE_SHEET_RANGE).execute()
                employee_data_cache = result.get("values", [])
                print(f"[愛子] 従業員キャッシュ更新完了: {len(employee_data_cache)-1}件")
            except Exception as e:
                print("[愛子] 従業員キャッシュ失敗:", e)
            time.sleep(interval_seconds)
    threading.Thread(target=update_loop, daemon=True).start()

# 全体ログキャッシュ
def refresh_global_chat_cache(interval_seconds=300):
    def update_loop():
        global global_chat_cache
        while True:
            try:
                global_chat_cache = load_all_chat_history(max_messages=300)
            except Exception as e:
                print("[愛子] 全体ログキャッシュ失敗:", e)
            time.sleep(interval_seconds)
    threading.Thread(target=update_loop, daemon=True).start()

# 会話ログ保存
def save_conversation_log(user_id, user_name, speaker, message):
    timestamp = datetime.datetime.now().isoformat()
    values = [[timestamp, user_id, user_name, speaker, message, '', '', '', '', '']]
    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range=LOG_RANGE_NAME,
            valueInputOption='USER_ENTERED',
            body={'values': values}
        ).execute()
    except Exception as e:
        logging.error(f"[愛子] 会話ログ保存失敗: {e}")

# 会話履歴読み込み
def load_recent_chat_history(user_name, limit=20):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range=LOG_RANGE_NAME).execute()
        rows = result.get("values", [])[1:]
        recent = [row for row in rows if len(row) >= 5 and row[2] == user_name][-limit:]
        return [{"role": "user" if row[3] == "user" else "assistant", "content": row[4]} for row in recent]
    except Exception as e:
        return []

def load_all_chat_history(max_messages=300):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range=LOG_RANGE_NAME).execute()
        rows = result.get("values", [])[1:][-max_messages:]
        return [{"role": "user" if row[3] == "user" else "assistant", "content": row[4]} for row in rows if len(row) >= 5]
    except Exception as e:
        return []

# ユーザーID→名前マップ
def load_user_id_map():
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID2, range=EMPLOYEE_SHEET_RANGE).execute()
        rows = result.get("values", [])[1:]
        return {row[12]: row[1] for row in rows if len(row) >= 13}
    except Exception as e:
        return {}

# 記憶削除（自然言語対応）
def delete_memory_entries(user_id, user_name, keyword):
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID4, range=COMPANY_SHEET_RANGE).execute()
        values = result.get("values", [])
        headers = values[0]
        rows = values[1:]
        filtered = [row for row in rows if keyword not in ''.join(row)]
        new_data = [headers] + filtered
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID4,
            range=COMPANY_SHEET_RANGE,
            valueInputOption='RAW',
            body={'values': new_data}
        ).execute()
        logging.info(f"[愛子] {user_name}の記憶 '{keyword}' を削除しました")
    except Exception as e:
        logging.error(f"[愛子] 記憶削除エラー: {e}")

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="愛子です。お友だち登録ありがとうございます。")
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    USER_ID_MAP = load_user_id_map()
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

    if "削除して" in user_message or "忘れて" in user_message:
        delete_memory_entries(user_id, user_name, user_message.replace("削除して", "").replace("忘れて", "").strip())

    personal_log = load_recent_chat_history(user_name)
    group_log = global_chat_cache[-30:]

    messages = [
        {"role": "system", "content": "あなたは社内秘書の愛子です。従業員情報・顧客情報・会話履歴・会社情報を自由に活用し、文脈に応じた自然な応答を行ってください。"},
        *group_log,
        *personal_log,
        {"role": "user", "content": user_message}
    ]

    response = client.chat.completions.create(model="gpt-4o", messages=messages)
    reply_text = response.choices[0].message.content.strip()

    save_conversation_log(user_id, user_name, "user", user_message)
    save_conversation_log(user_id, user_name, "assistant", reply_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    keep_server_awake()
    refresh_employee_data_cache()
    refresh_global_chat_cache()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
