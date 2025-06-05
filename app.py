import os
import traceback
import logging
import datetime
import threading
import time
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz

load_dotenv()

# 日本標準時 (JST) タイムゾーン
JST = pytz.timezone('Asia/Tokyo')

def now_jst():
    return datetime.datetime.now(JST)

def get_time_based_greeting():
    hour = now_jst().hour
    if 5 <= hour < 10:
        return "おっはー。"
    elif 10 <= hour < 18:
        return "やっはろー。"
    elif 18 <= hour < 23:
        return "おっつ〜。"
    else:
        return "ねむねむ。"

app = Flask(__name__)

# LINE Bot設定
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# OpenAIクライアント
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Google Sheets設定
SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

SPREADSHEET_IDS = [
    os.getenv('SPREADSHEET_ID1'),
    os.getenv('SPREADSHEET_ID2'),
    os.getenv('SPREADSHEET_ID3'),
    os.getenv('SPREADSHEET_ID4'),
    os.getenv('SPREADSHEET_ID5')
]

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
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="愛子です。お友だち登録ありがとうございます。")
    )

def search_employee_info(query):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_IDS[0],  # 従業員情報
            range='従業員情報!A1:Z'
        ).execute()
        rows = result.get("values", [])

        for row in rows:
            if any(query in cell for cell in row):
                return "🔎 社内情報から見つけました: " + ", ".join(row)
        return "⚠️ 社内情報でも見つかりませんでした。"
    except Exception as e:
        logging.error("社内スプレッドシート検索エラー: %s", e)
        return "⚠️ 情報検索中にエラーが発生しました。"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()

    greeting = get_time_based_greeting()
    greeting_keywords = ["おっはー", "やっはろー", "おっつ〜", "ねむねむ"]

    messages = [
        {"role": "system", "content": "あなたは社内アシスタントAI『愛子』です。以下のメッセージに丁寧に回答してください。"},
        {"role": "user", "content": user_message}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        reply_text = response.choices[0].message.content.strip()

        if any(kw in reply_text for kw in ["申し訳", "できません"]):
            reply_text = search_employee_info(user_message)

        if not any(reply_text.startswith(g) for g in greeting_keywords):
            reply_text = f"{greeting}{reply_text}"

    except Exception as e:
        logging.error("OpenAI 応答失敗: %s", e)
        reply_text = "⚠️ 応答に失敗しました。政美さんにご連絡ください。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
