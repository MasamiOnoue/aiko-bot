# app.py（更新版）

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

from aiko_greeting import now_jst, get_time_based_greeting, get_user_callname
from company_info import (
    get_employee_info,
    get_partner_info,
    get_company_info,
    get_conversation_log,
    get_experience_log,
    write_conversation_log,
    write_experience_log,
    write_company_info,
)
from aiko_diary_report import generate_daily_report, send_daily_report

load_dotenv()

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    # 呼ばれ方を取得
    callname = get_user_callname(user_id)
    greeting = get_time_based_greeting(user_id)

    # 応答テキストの組み立て
    reply_text = f"{greeting} {callname}、何かご用でしょうか？"

    # 会話ログへ記録
    write_conversation_log(
        timestamp=now_jst().isoformat(),
        user_id=user_id,
        user_name="不明",
        speaker="ユーザー",
        message=user_message,
        category="未分類",
        message_type="テキスト",
        topic="",
        status="OK",
        sentiment=""
    )

    # 応答ログも記録
    write_conversation_log(
        timestamp=now_jst().isoformat(),
        user_id=user_id,
        user_name="不明",
        speaker="愛子",
        message=reply_text,
        category="挨拶",
        message_type="テキスト",
        topic="",
        status="OK",
        sentiment=""
    )

    # 応答を送信
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# 愛子日報送信エンドポイント（任意で呼び出し）
@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
