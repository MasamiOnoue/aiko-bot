# app.py

import os
import sys
import logging
from dotenv import load_dotenv
load_dotenv()

# 相対パスで write_read_commands を追加
sys.path.append(os.path.join(os.path.dirname(__file__), 'write_read_commands'))

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
from openai import OpenAI

from linebot import LineBotApi, WebhookHandler

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from sheets_service import get_google_sheets_service
from handle_message_logic import handle_message_logic 

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

app = Flask(__name__)

sheet_service = get_google_sheets_service()

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    print("✅ LINE Webhook受信:", body)
    signature = request.headers.get("X-Line-Signature")
    print("📩 LINE Signature:", signature)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ 署名不一致エラー")
        abort(400)
    return "OK", 200

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    handle_message_logic(event, sheet_service, line_bot_api)
    
@app.route("/daily_report", methods=["GET"])
def daily_report():
    from aiko_diary_report import send_daily_report
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
