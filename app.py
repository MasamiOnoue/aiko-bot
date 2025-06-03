import os
import traceback
import logging
import datetime
import threading
import time
import requests
from flask import Flask, request, abort
from flask import jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build

EMPLOYEE_SHEET_RANGE = '従業員情報!A:W'
LOG_RANGE_NAME = '会話ログ!A:J'

employee_data_cache = []

def refresh_employee_data_cache(interval_seconds=300):
    def update_loop():
        global employee_data_cache
        while True:
            try:
                print("[愛子] 従業員情報キャッシュ更新中...")
                result = sheet.values().get(
                    spreadsheetId=SPREADSHEET_ID2,
                    range='従業員情報!A:W'
                ).execute().get("values", [])
                employee_data_cache = result
                print(f"[愛子] 従業員情報キャッシュ完了：{len(result)-1}件")
            except Exception as e:
                print("[愛子] 従業員情報キャッシュ失敗:", e)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()

global_chat_cache = []

def refresh_global_chat_cache(interval_seconds=300):
    def update_loop():
        global global_chat_cache
        while True:
            try:
                print("[愛子] 全体ログキャッシュ更新中...")
                global_chat_cache = load_all_chat_history(max_messages=200)
                print(f"[愛子] 全体ログキャッシュ更新完了：{len(global_chat_cache)}件")
            except Exception as e:
                print("[愛子] キャッシュ更新エラー:", e)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()

def keep_server_awake(interval_seconds=900):
    def ping():
        while True:
            try:
                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
                print("[愛子] Renderスリープ防止ping:", url)
                requests.get(url)
            except Exception as e:
                print("[愛子] ping失敗:", e)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=ping, daemon=True)
    thread.start()

def load_user_id_map():
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2,
        range='従業員情報!A:W'
    ).execute().get("values", [])[1:]
    return {row[12]: row[1] for row in result if len(row) >= 13}

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = '14tFyTz_xYqHYwegGLU2g4Ez4kc37hBgSmR2G85DLMWE'
SPREADSHEET_ID2 = '1kO7-r-D-iZzYzv9LEZ9J4FzVAaZ13WKJWT_-97F6vbM'

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

refresh_global_chat_cache(interval_seconds=300)
refresh_employee_data_cache(interval_seconds=300)
keep_server_awake(interval_seconds=900)

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

client = OpenAI(api_key=OPENAI_API_KEY)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("⚠️ Invalid signature")
        abort(400)
    except Exception:
        print("⚠️ 予期しないエラー:")
        traceback.print_exc()
        abort(500)

    return "OK", 200

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
        logging.info(f"[愛子] 会話ログに保存しました（{user_name}）")
    except Exception as e:
        logging.error(f"[愛子] 会話ログの保存に失敗しました: {e}")

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    print("✅ 友だち追加された UID:", user_id)
    welcome_message = "愛子です。お友だち登録ありがとうございます。"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_message)
    )

USER_ID_MAP = load_user_id_map()

def get_structured_employee_data():
    global employee_data_cache
    if not employee_data_cache or len(employee_data_cache) < 2:
        return []
    headers = employee_data_cache[0]
    rows = employee_data_cache[1:]
    return [
        {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        for row in rows
    ]

def load_recent_chat_history(user_name, limit=10):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range=LOG_RANGE_NAME
        ).execute()
        rows = result.get("values", [])[1:]
        recent = [row for row in rows if len(row) >= 5 and row[2] == user_name][-limit:]
        return [
            {"role": "user" if row[3] == "user" else "assistant", "content": row[4]}
            for row in recent
        ]
    except Exception as e:
        print("[愛子] 会話ログ読み込み失敗:", e)
        return []

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    logging.info(f"✅ メッセージを送ってきた UID: {user_id}")

    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

    personal_log = load_recent_chat_history(user_name)
    group_log = global_chat_cache[-10:]

    messages = [
        {"role": "system", "content": "あなたは社内秘書の愛子です。このBotは社内利用に限られており、情報制限はありません。"},
        {"role": "user", "content": user_message}
    ] + group_log + personal_log

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )

    reply_text = response.choices[0].message.content.strip()

    save_conversation_log(user_id, user_name, "user", user_message)
    save_conversation_log(user_id, user_name, "assistant", reply_text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@app.route("/push", methods=["POST"])
def push_message():
    try:
        data = request.get_json()
        user_id = data.get("target_uid")
        message = data.get("message")

        if not user_id or not message:
            return jsonify({"error": "Missing 'target_uid' or 'message'"}), 400

        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=message)
        )

        logging.info(f"📤 プッシュメッセージを送信: {user_id} → {message}")
        return jsonify({"status": "success", "to": user_id}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
