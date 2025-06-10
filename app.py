# main.py（旧 app.py）統合改良版

import os
import logging
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from company_info_load import get_google_sheets_service
from handle_message_logic import handle_message_logic
from aiko_diary_report import send_daily_report

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 環境変数の読み込み
load_dotenv()

# Flaskアプリの初期化
app = Flask(__name__)

# LINE APIの初期化
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_ADMIN_USER_ID = os.getenv("LINE_ADMIN_USER_ID")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    logging.critical("❌ LINEの環境変数が未設定です")
    raise EnvironmentError("LINEの環境変数が未設定です")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Sheetsサービス
sheet_service = get_google_sheets_service()

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logging.warning("❗ 無効な署名を検出しました")
        abort(400)
    except Exception as e:
        logging.error(f"❌ ハンドラ処理中の例外: {e}")
        abort(500)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        handle_message_logic(event, sheet_service, line_bot_api)
    except Exception as e:
        logging.error(f"❌ メッセージ処理失敗: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="申し訳ありません、処理中にエラーが発生しました。"))

@app.route("/daily_report", methods=["GET"])
def daily_report():
    try:
        send_daily_report(line_bot_api, LINE_ADMIN_USER_ID)
        return "日報を送信しました"
    except Exception as e:
        logging.error(f"❌ 日報送信失敗: {e}")
        return "日報の送信に失敗しました"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
