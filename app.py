# app.py（メインLINE Bot処理）

import os
import logging
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from company_info import get_google_sheets_service, append_conversation_log, SPREADSHEET_ID1
from aiko_greeting import now_jst, get_time_based_greeting

app = Flask(__name__)

# LINE API 認証
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# LINE Webhook エンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# メッセージ受信時
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    reply_token = event.reply_token

    # JSTタイムスタンプ
    timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")

    # 応答メッセージを生成
    greeting = get_time_based_greeting()
    reply_text = f"{greeting} ご用件は何ですか？"

    # LINE返信
    line_bot_api.reply_message(reply_token, TextSendMessage(text=reply_text))

    # 会話ログをGoogle Sheetsに記録
    sheet_service = get_google_sheets_service()
    if sheet_service:
        append_conversation_log(
            sheet_service,
            SPREADSHEET_ID1,
            timestamp=timestamp,
            user_id=user_id,
            user_name="不明",
            speaker="ユーザー",
            message=user_message,
            status="OK"
        )
        append_conversation_log(
            sheet_service,
            SPREADSHEET_ID1,
            timestamp=timestamp,
            user_id=user_id,
            user_name="不明",
            speaker="AI",
            message=reply_text,
            status="OK"
        )

if __name__ == "__main__":
    app.run(debug=True)
