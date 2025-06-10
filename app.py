# app.py　メイン関数

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage
from dotenv import load_dotenv
from company_info_load import get_google_sheets_service
from handle_message_logic import handle_message_logic
from aiko_diary_report import send_daily_report

# 環境変数の読み込み
load_dotenv()

# Flaskアプリの初期化
app = Flask(__name__)

# LINE APIの初期化
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Google Sheetsサービス
sheet_service = get_google_sheets_service()

# LINEコールバックエンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# LINEメッセージ受信時の処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    handle_message_logic(event, sheet_service, line_bot_api)

# 毎日の日報送信エンドポイント
@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

# サーバー起動
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
