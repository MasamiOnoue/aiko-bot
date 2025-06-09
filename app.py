# app.py（完全統合版）

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
import openai

from aiko_greeting import (
    now_jst,
    get_time_based_greeting,
    get_user_callname,
    is_attendance_related,
    is_topic_changed,
    get_user_status,
    update_user_status,
    reset_user_status,
    forward_message_to_others,
    get_user_name_for_sheet
)
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
    greeting = get_time_based_greeting()

    status = get_user_status(user_id)
    step = status.get("step", 0)

    # 出社・遅刻関連メッセージへの対応ループ
    if step == 0 and is_attendance_related(user_message):
        update_user_status(user_id, 1)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="わかりました。どなたかにお伝えしますか？"))
        return

    if step == 1:
        if user_message == "はい":
            update_user_status(user_id, 2)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="全員でいいですか？"))
            return
        elif user_message == "いいえ":
            reset_user_status(user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解しました。お気をつけて。"))
            return
        elif is_topic_changed(user_message):
            reset_user_status(user_id)

    elif step == 2:
        if user_message == "はい":
            all_user_ids = load_all_user_ids()
            forward_message_to_others(line_bot_api, callname, "出社予定・遅刻連絡がありました。", [uid for uid in all_user_ids if uid != user_id])
            reset_user_status(user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="全員にお伝えしました。お気をつけて。"))
            return
        elif user_message == "いいえ":
            update_user_status(user_id, 3)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="誰に送りますか？"))
            return
        elif is_topic_changed(user_message):
            reset_user_status(user_id)

    elif step == 3:
        recipients = []
        employee_info = get_employee_info(sheet_service)
        for row in employee_info:
            if len(row) >= 4 and any(name in user_message for name in row[3:4]):
                if len(row) >= 12:
                    recipients.append(row[11])
        if recipients:
            forward_message_to_others(line_bot_api, callname, "出社予定・遅刻連絡がありました。", recipients)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{row[3]}さんに送ります。お気をつけて。"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="該当者が見つかりませんでした。"))
        reset_user_status(user_id)
        return

    if is_topic_changed(user_message):
        reset_user_status(user_id)

    try:
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
            system_instruction = "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示しなさい。"
            user_prompt = f"{system_instruction}\n\nユーザーの入力: {user_message}"
            reply_text = generate_contextual_reply(user_id, user_prompt)

    except Exception as e:
        reply_text = f"申し訳ありません。現在応答できませんでした（{e}）"

    write_conversation_log(sheet_service, now_jst().isoformat(), user_id, DEFAULT_USER_NAME, "ユーザー", user_message, "OK")
    write_conversation_log(sheet_service, now_jst().isoformat(), user_id, DEFAULT_USER_NAME, "愛子", reply_text, "OK")

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
