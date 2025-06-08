# app.py（最小構成 + 外部関数読み込み）

import os
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from aiko_greeting import now_jst, get_time_based_greeting
from company_info import (
    get_google_sheets_service,
    get_conversation_log,
    get_employee_info,
    get_partner_info,
    get_company_info,
    get_aiko_experience_log
)

load_dotenv()

app = Flask(__name__)

# LINE Messaging API トークン類
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Google Sheets API サービスを初期化
gsheet_service = get_google_sheets_service()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    # 挨拶テスト
    if "あいさつ" in user_message:
        reply_text = get_time_based_greeting()
    else:
        reply_text = f"あなたのメッセージ: {user_message}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
