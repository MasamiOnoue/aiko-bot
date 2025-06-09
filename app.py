# app.py

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from aiko_greeting import (
    now_jst,
    get_time_based_greeting,
    is_attendance_related,
    is_topic_changed,
    get_user_status,
    update_user_status,
    reset_user_status,
    forward_message_to_others,
    get_user_name_for_sheet,
    get_aiko_official_email,
    fetch_latest_email,
    has_recent_greeting,
    record_greeting_time,
    normalize_greeting
)
from company_info import (
    search_employee_info_by_keywords,
    classify_conversation_category
)
from company_info_load import (
    get_employee_info,
    get_partner_info,
    get_company_info,
    get_conversation_log,
    get_experience_log,
    load_all_user_ids,
    get_user_callname_from_uid,
    get_google_sheets_service
)
from company_info_save import (
    write_conversation_log,
    write_aiko_experience_log,
    write_company_info,
    write_employee_info,
    write_partner_info
)
from aiko_diary_report import generate_daily_report, send_daily_report
from aiko_mailer import draft_email_for_user, send_email_with_confirmation, get_user_email_from_uid
from mask_word import (
    contains_sensitive_info,
    mask_sensitive_data,
    unmask_sensitive_data,
    rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply

load_dotenv()

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
    from handle_message_logic import handle_message_logic
    handle_message_logic(event, sheet_service, line_bot_api)

@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
