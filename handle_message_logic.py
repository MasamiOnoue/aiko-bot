# handle_message_logic.py  LINEメッセージを受け取ったときのメイン処理

from linebot.models import TextSendMessage
from aiko_greeting import (
    now_jst, get_time_based_greeting, is_attendance_related, is_topic_changed,
    get_user_status, update_user_status, reset_user_status, forward_message_to_others,
    fetch_latest_email, has_recent_greeting, record_greeting_time, normalize_greeting
)
from company_info import (
    search_employee_info_by_keywords, classify_conversation_category
)
from aiko_mailer import (
    draft_email_for_user, send_email_with_confirmation, get_user_email_from_uid
)
from mask_word import (
    contains_sensitive_info, mask_sensitive_data,
    unmask_sensitive_data, rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply
from openai_client import client
from information_writer import write_conversation_log
from company_info_load import (
    get_employee_info, get_partner_info, get_company_info, get_conversation_log, get_experience_log,
    load_all_user_ids, get_user_callname_from_uid
)
import logging

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

def log_aiko_reply(user_id, user_name, message, speaker, category, message_type, topic, status, sentiment=""):
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "timestamp": timestamp,
            "user_id": user_id,
            "user_name": user_name,
            "speaker": speaker,
            "message": message,
            "category": category,
            "message_type": message_type,
            "topic": topic,
            "status": status,
            "sentiment": sentiment
        }
        logging.info(f"📤 log_aiko_reply payload: {payload}")
        write_conversation_log(**payload)
    except Exception as e:
        import traceback
        logging.error("❌ log_aiko_reply エラー:")
        logging.error(traceback.format_exc())

def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    user_name = get_user_callname_from_uid(user_id) or DEFAULT_USER_NAME

    registered_uids = load_all_user_ids()
    if user_id not in registered_uids:
        log_aiko_reply(user_id, user_name, user_message, speaker="ユーザー", category="未分類", message_type="テキスト", topic="未設定", status="NG")
        reply = "申し訳ありません。このサービスは社内専用です。"
        log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="権限エラー", message_type="テキスト", topic="認証", status="NG")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    category = classify_conversation_category(user_message) or "未分類"
    log_aiko_reply(user_id, user_name, user_message, speaker="ユーザー", category=category, message_type="テキスト", topic="未設定", status="OK")

    callname = user_name
    greet_key = normalize_greeting(user_message)
    if greet_key and not has_recent_greeting(user_id, greet_key):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greet_key)
        reply = f"{greeting}{callname}"
        log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="挨拶", message_type="テキスト", topic="挨拶", status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if "最新メール" in user_message or "メール見せて" in user_message:
        email_text = fetch_latest_email() or "最新のメールは見つかりませんでした。"
        log_aiko_reply(user_id, user_name, email_text, speaker="愛子", category="メール表示", message_type="テキスト", topic="社内メール", status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=email_text[:100]))
        return

    if "にメールを送って" in user_message:
        target = user_message.replace("にメールを送って", "").strip()
        draft_body = draft_email_for_user(user_id, target)
        update_user_status(user_id, 100)
        update_user_status(user_id + "_target", target)
        reply = f"この内容で{target}にメールを送りますか？"
        log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="メール確認", message_type="テキスト", topic=target, status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    status = get_user_status(user_id) or {}
    step = status.get("step", 0)
    if step == 100:
        target = get_user_status(user_id + "_target")
        user_email = get_user_email_from_uid(user_id)
        if user_message == "はい":
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=user_email)
            reply = f"{target}にメールを送信しました。"
        else:
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=None)
            reply = "メールはあなたにだけ送信しました。内容を確認してください。"
        reset_user_status(user_id)
        reset_user_status(user_id + "_target")
        log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="メール送信", message_type="テキスト", topic=target, status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if step == 200:
        fulltext = get_user_status(user_id + "_fulltext")
        if user_message == "はい":
            user_email = get_user_email_from_uid(user_id)
            send_email_with_confirmation(sender_uid=user_id, to_name=user_email, cc=None, body=fulltext)
            reply = "メールで送信しました。ご確認ください。"
        else:
            reply = "了解しました。必要があればまた聞いてください。"
        reset_user_status(user_id)
        reset_user_status(user_id + "_fulltext")
        log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="メール送信確認", message_type="テキスト", topic="AI応答", status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    employee_info = get_employee_info()
    reply = search_employee_info_by_keywords(user_message, employee_info)
    if not reply:
        try:
            if contains_sensitive_info(user_message):
                combined = []
                for dataset in [get_employee_info(), get_partner_info(), get_company_info(), get_conversation_log(), get_experience_log()]:
                    combined.extend([str(item) for item in dataset if any(w in str(item) for w in user_message.split())])
                hits = combined[:MAX_HITS] or ["該当情報が見つかりませんでした。"]
                masked_input, mask_map = mask_sensitive_data("\n".join(hits))
                reply_masked = rephrase_with_masked_text(masked_input)
                reply = unmask_sensitive_data(reply_masked, mask_map)
            else:
                system_instruction = "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示し、LINE返信は100文字以内にまとめてください。"
                prompt = f"{system_instruction}\n\nユーザーの入力: {user_message}"
                reply = generate_contextual_reply(user_id, prompt)
        except Exception as e:
            reply = f"申し訳ありません。現在応答できません（{e}）"

    if len(reply) > 80:
        update_user_status(user_id, 200)
        update_user_status(user_id + "_fulltext", reply)
        short_reply = "もっと情報がありますがLINEでは送れないのでメールで送りますか？"
        log_aiko_reply(user_id, user_name, short_reply, speaker="愛子", category="長文応答", message_type="テキスト", topic="AI応答", status="OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return

    short_reply = reply[:100]
    log_aiko_reply(user_id, user_name, reply, speaker="愛子", category="通常応答", message_type="テキスト", topic="AI応答", status="OK")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
