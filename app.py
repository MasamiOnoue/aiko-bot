
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

# 環境変数と設定
EMPLOYEE_SHEET_RANGE = '従業員情報!A:W'
LOG_RANGE_NAME = '会話ログ!A:J'
COMPANY_SHEET_RANGE = '会社情報!A:Z'
CUSTOMER_SHEET_RANGE = '顧客情報!A:T'

employee_data_cache = []
global_chat_cache = []
company_info_cache = []
customer_data_cache = []

# Flask アプリ初期化
app = Flask(__name__)
load_dotenv()
logging.basicConfig(level=logging.INFO)

# 認証とAPIクライアント
SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv("SPREADSHEET_ID1")  # 会話ログ
SPREADSHEET_ID2 = os.getenv("SPREADSHEET_ID2")  # 従業員情報
SPREADSHEET_ID3 = os.getenv("SPREADSHEET_ID3")  # 顧客情報
SPREADSHEET_ID4 = os.getenv("SPREADSHEET_ID4")  # 会社情報

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheet = build('sheets', 'v4', credentials=creds).spreadsheets()

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# キャッシュ更新関数
def refresh_cache(func, interval=300):
    def loop():
        while True:
            try:
                func()
            except Exception as e:
                logging.error(f"[愛子] キャッシュ更新失敗: {e}")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()

def update_employee_data():
    global employee_data_cache
    employee_data_cache = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2, range=EMPLOYEE_SHEET_RANGE
    ).execute().get("values", [])

def update_company_info():
    global company_info_cache
    company_info_cache = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID4, range=COMPANY_SHEET_RANGE
    ).execute().get("values", [])

def update_customer_data():
    global customer_data_cache
    customer_data_cache = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID3, range=CUSTOMER_SHEET_RANGE
    ).execute().get("values", [])

def update_chat_history():
    global global_chat_cache
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID1, range=LOG_RANGE_NAME
    ).execute().get("values", [])[1:]
    global_chat_cache = result[-300:]

# Render スリープ防止
def keep_server_awake(interval=900):
    def ping():
        while True:
            try:
                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
                requests.get(url)
            except Exception as e:
                logging.warning(f"[愛子] ping失敗: {e}")
            time.sleep(interval)
    threading.Thread(target=ping, daemon=True).start()

# 会話ログ保存
def save_conversation(user_id, user_name, speaker, message):
    now = datetime.datetime.now().isoformat()
    values = [[now, user_id, user_name, speaker, message, '', '', '', '', '']]
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID1,
        range=LOG_RANGE_NAME,
        valueInputOption='USER_ENTERED',
        body={'values': values}
    ).execute()

# メモリ削除
def delete_memory_entries(user_id, user_name, keyword):
    global company_info_cache
    values = company_info_cache
    headers = values[0]
    rows = values[1:]
    updated_rows = [row for row in rows if keyword not in row[4] or row[1] != user_id]
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID4,
        range=COMPANY_SHEET_RANGE,
        valueInputOption='USER_ENTERED',
        body={'values': [headers] + updated_rows}
    ).execute()

# ID → 名前の変換
def load_user_id_map():
    rows = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2, range=EMPLOYEE_SHEET_RANGE
    ).execute().get("values", [])[1:]
    return {row[12]: row[1] for row in rows if len(row) >= 13}

USER_ID_MAP = load_user_id_map()

# LINE Webhook
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        traceback.print_exc()
        abort(500)
    return "OK", 200

@handler.add(FollowEvent)
def handle_follow(event):
    uid = event.source.user_id
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="愛子です。お友だち登録ありがとうございます。")
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

    if "削除して" in user_message or "忘れて" in user_message:
        keyword = user_message.replace("削除して", "").replace("忘れて", "").strip()
        delete_memory_entries(user_id, user_name, keyword)
        reply = f"「{keyword}」に関する情報を削除しました。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    personal_log = [
        {"role": "user" if row[3] == "user" else "assistant", "content": row[4]}
        for row in global_chat_cache[-20:] if row[2] == user_name
    ]
    group_log = [
        {"role": "user" if row[3] == "user" else "assistant", "content": row[4]}
        for row in global_chat_cache[-30:]
    ]

    messages = [
        {"role": "system", "content": "あなたは社内秘書の愛子です。すべての情報（従業員・顧客・会社・会話履歴）を文脈に活用して構いません。"},
        {"role": "user", "content": user_message}
    ] + group_log + personal_log

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    reply_text = response.choices[0].message.content.strip()

    save_conversation(user_id, user_name, "user", user_message)
    save_conversation(user_id, user_name, "assistant", reply_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# プッシュメッセージAPI
@app.route("/push", methods=["POST"])
def push_message():
    data = request.get_json()
    uid = data.get("target_uid")
    msg = data.get("message")
    if not uid or not msg:
        return jsonify({"error": "target_uidまたはmessageが不足しています"}), 400
    line_bot_api.push_message(uid, TextSendMessage(text=msg))
    return jsonify({"status": "success"}), 200

# 起動時処理
if __name__ == "__main__":
    refresh_cache(update_employee_data)
    refresh_cache(update_company_info)
    refresh_cache(update_customer_data)
    refresh_cache(update_chat_history)
    keep_server_awake()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
