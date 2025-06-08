# app.py（完全統合版）

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
import openai

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
    load_all_user_ids,
    get_user_callname_from_uid,
    get_google_sheets_service
)
from aiko_diary_report import generate_daily_report, send_daily_report
from mask_word import (
    contains_sensitive_info,
    mask_sensitive_data,
    unmask_sensitive_data,
    rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
sheet_service = get_google_sheets_service()

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
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

    callname = get_user_callname_from_uid(user_id)
    greeting = get_time_based_greeting(user_id)

    try:
        # 個人情報が含まれる場合はマスク処理へ
        if contains_sensitive_info(user_message):
            sources = [
                get_employee_info(sheet_service),
                get_partner_info(sheet_service),
                get_company_info(sheet_service),
                get_conversation_log(sheet_service),
                get_experience_log(sheet_service)
            ]
            hits = [str(item) for sublist in sources for item in sublist if any(w in str(item) for w in user_message.split())]
            hits = hits[:MAX_HITS] if hits else ["該当情報が見つかりませんでした。"]

            masked_input, mask_map = mask_sensitive_data("\n".join(hits))
            masked_reply = rephrase_with_masked_text(masked_input)
            reply_text = unmask_sensitive_data(masked_reply, mask_map)
        else:
            reply_text = generate_contextual_reply(user_id, user_message)

    except Exception as e:
        reply_text = f"申し訳ありません。現在応答できませんでした（{e}）"

    # 会話ログの記録（ユーザー）
    write_conversation_log(
        sheet_service,
        timestamp=now_jst().isoformat(),
        user_id=user_id,
        user_name=DEFAULT_USER_NAME,
        speaker="ユーザー",
        message=user_message,
        status="OK"
    )

    # 会話ログの記録（愛子）
    write_conversation_log(
        sheet_service,
        timestamp=now_jst().isoformat(),
        user_id=user_id,
        user_name=DEFAULT_USER_NAME,
        speaker="愛子",
        message=reply_text,
        status="OK"
    )

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
