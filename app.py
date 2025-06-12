# app.py

import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from aiko_conversation_log import send_conversation_log
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
    body = request.get_data(as_text=True)  # ✅ 最初に定義
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
    user_id = event.source.user_id
    user_message = event.message.text
    user_name = get_user_callname_from_uid(user_id)  # ← ユーザー名を取得
    print("📥 ユーザーメッセージ:", event.message.text)  # デバッグ用
    reply_text = ""
    reply_text_short = ""

    category = classify_conversation_category(user_message)
    try:
        send_conversation_log(
            timestamp=now_jst().isoformat(),
            user_id=user_id,
            user_name=user_name,
            speaker="ユーザー",
            message=user_message,
            category=category,
            message_type="テキスト",
            topic="テスト",
            status="OK",
            sentiment=""
        )
    except Exception as e:
        print(f"❌ 会話ログ送信失敗: {e}")

    registered_uids = load_all_user_ids()
    if user_id not in registered_uids:
        #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, category, "テキスト", "テスト", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="申し訳ありません。このサービスは社内専用です。"))
        return

    callname = get_user_callname_from_uid(user_id)

    category = normalize_greeting(user_message)
    if category and not has_recent_greeting(user_id, category):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), category)
        #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{greeting}{callname}"))
        return

    if "最新メール" in user_message or "メール見せて" in user_message:
        email_text = fetch_latest_email() or "最新のメールは見つかりませんでした。"
        #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=email_text[:100]))
        return

    if "にメールを送って" in user_message:
        target = user_message.replace("にメールを送って", "").strip()
        draft_body = draft_email_for_user(user_id, target)
        update_user_status(user_id, 100)
        update_user_status(user_id + "_target", target)
        #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"この内容で{target}にメールを送りますか？"))
        return

    status = get_user_status(user_id)
    step = status.get("step", 0)
    if step == 100:
        target = get_user_status(user_id + "_target")
        user_email = get_user_email_from_uid(user_id)
        if user_message == "はい":
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=user_email)
            reset_user_status(user_id)
            reset_user_status(user_id + "_target")
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{target}にメールを送信しました。"))
            return
        elif user_message == "いいえ":
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=None)
            reset_user_status(user_id)
            reset_user_status(user_id + "_target")
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="メールはあなたにだけ送信しました。内容を確認してください。"))
            return

    if step == 200:
        fulltext = get_user_status(user_id + "_fulltext")
        if user_message == "はい":
            user_email = get_user_email_from_uid(user_id)
            send_email_with_confirmation(sender_uid=user_id, to_name=user_email, cc=None, body=fulltext)
            reset_user_status(user_id)
            reset_user_status(user_id + "_fulltext")
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="メールで送信しました。ご確認ください。"))
            return
        elif user_message == "いいえ":
            reset_user_status(user_id)
            reset_user_status(user_id + "_fulltext")
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解しました。必要があればまた聞いてください。"))
            return

    if step == 0 and is_attendance_related(user_message):
        update_user_status(user_id, 1)
        #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="わかりました。どなたかにお伝えしますか？"))
        return

    if step == 1:
        if user_message == "はい":
            update_user_status(user_id, 2)
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="全員でいいですか？"))
            return
        elif user_message == "いいえ":
            reset_user_status(user_id)
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解しました。お気をつけて。"))
            return
        elif is_topic_changed(user_message):
            reset_user_status(user_id)

    elif step == 2:
        if user_message == "はい":
            all_user_ids = load_all_user_ids()
            forward_message_to_others(line_bot_api, callname, "出社予定・遅刻連絡がありました。", [uid for uid in all_user_ids if uid != user_id])
            reset_user_status(user_id)
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="全員にお伝えしました。お気をつけて。"))
            return
        elif user_message == "いいえ":
            update_user_status(user_id, 3)
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
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
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"{row[3]}に送ります。お気をつけて。"))
        else:
            #write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text_short, "テキスト", "テスト", "OK")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="該当者が見つかりませんでした。"))
        reset_user_status(user_id)
        return

    if is_topic_changed(user_message):
        reset_user_status(user_id)

    employee_info_list = get_employee_info(sheet_service)
    keyword_reply = search_employee_info_by_keywords(user_message, employee_info_list)
    if keyword_reply:
        reply_text = keyword_reply
    else:
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
                system_instruction = "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示し、LINE返信は100文字以内にまとめてください。"
                user_prompt = f"{system_instruction}\n\nユーザーの入力: {user_message}"
                reply_text = generate_contextual_reply(user_id, user_prompt)

        except Exception as e:
            reply_text = f"申し訳ありません。現在応答できませんでした（{e}）"
    
    if len(reply_text) > 80:
        update_user_status(user_id, 200)
        update_user_status(user_id + "_fulltext", reply_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="もっと情報がありますがLINEでは遅れないのでメールで送りますか？"))
        return

    reply_text_short = reply_text[:100]
    try:
        send_conversation_log(
            timestamp=now_jst().isoformat(),
            user_id=user_id,
            user_name="愛子",
            speaker="愛子",
            message=reply_text_short,
            category="テキスト",
            message_type="テキスト",
            topic="テスト",
            status="OK",
            sentiment=""
        )
    except Exception as e:
        print(f"❌ 最終返信ログ送信失敗: {e}")

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text_short))

@app.route("/daily_report", methods=["GET"])
def daily_report():
    user_id = os.getenv("LINE_ADMIN_USER_ID")
    send_daily_report(line_bot_api, user_id)
    return "日報を送信しました"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
