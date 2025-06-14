# handle_message_logic.py  LINEメッセージを受け取ったときのメイン処理

import os
import logging

from datetime import datetime
from linebot.models import TextSendMessage
from aiko_greeting import (
    now_jst, get_time_based_greeting, is_attendance_related, is_topic_changed,
    get_user_status, update_user_status, reset_user_status, forward_message_to_others,
    has_recent_greeting, record_greeting_time, normalize_greeting, classify_conversation_category
)
from company_info import (
    search_employee_info_by_keywords,
    search_partner_info_by_keywords, 
    search_company_info_log,   
    search_aiko_experience_log,      
    search_conversation_log,    
    log_if_all_searches_failed, 
    get_user_callname_from_uid,
    load_all_user_ids
)
from information_reader import (
    read_employee_info,
    read_partner_info, 
    read_company_info,  
    read_conversation_log, 
    read_aiko_experience_log,
    read_task_info, 
    read_attendance_log 
)

# 勤怠ログ記録のためのライター関数をインポート
from information_writer import write_attendance_log

from aiko_mailer import (
    draft_email_for_user, send_email_with_confirmation, get_user_email_from_uid, fetch_latest_email
)
from mask_word import (
    contains_sensitive_info, mask_sensitive_data,
    unmask_sensitive_data, rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply
from openai_client import client
from aiko_helpers import log_aiko_reply

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

# 出勤記録用関数
from attendance_logger import log_attendance_from_qr

def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id.strip().upper()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_message = event.message.text.strip()
    user_name = get_user_callname_from_uid(user_id) or DEFAULT_USER_NAME

    # QRコードによる出勤処理
    if user_message.startswith("QR出勤:" ):
        qr_code = user_message.replace("QR出勤:", "").strip()
        spreadsheet_id = os.getenv("SPREADSHEET_ID7")
        if not spreadsheet_id:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="SPREADSHEET_ID7 が設定されていません。"))
            return
        result = log_attendance_from_qr(user_id, qr_code, spreadsheet_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
        return

    category = classify_conversation_category(user_message) or "未分類"
    log_aiko_reply(
        timestamp=timestamp,
        user_id=user_id,
        user_name=user_name,
        speaker="ユーザー",
        reply=user_message,
        category=category,
        message_type="テキスト",
        topics="不明",
        status="OK",
        topic="不明",
        sentiment="不明"
    )
    registered_uids = load_all_user_ids()

    logging.info(f"✅ 取得済み社内UIDリスト: {registered_uids}")
    logging.info(f"👤 現在のユーザーID: {user_id}")

    if user_id not in registered_uids:
        reply = "申し訳ありません。このサービスは社内専用です。"
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=reply,
            category="権限エラー",
            message_type="テキスト",
            topics="警告",
            status="NG",
            topic="認証",
            sentiment="冷静"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    greet_key = normalize_greeting(user_message)
    if greet_key and not has_recent_greeting(user_id, greet_key):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greet_key)
        reply = greeting
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=reply,
            category="挨拶",
            message_type="テキスト",
            topics="挨拶",
            status="OK",
            topic="挨拶",
            sentiment="ポジティブ"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if "最新メール" in user_message or "メール見せて" in user_message:
        email_text = fetch_latest_email() or "最新のメールは見つかりませんでした。"
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=email_text,
            category="メール",
            message_type="テキスト",
            topics="社内メール",
            status="OK",
            topic="社内メール",
            sentiment="冷静"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=email_text[:100]))
        return

    if "にメールを送って" in user_message:
        target = user_message.replace("にメールを送って", "").strip()
        draft_body = draft_email_for_user(user_id, target)
        update_user_status(user_id, 100)
        update_user_status(user_id + "_target", target)
        reply = f"この内容で{target}にメールを送りますか？"
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=reply,
            category="メール確認",
            message_type="テキスト",
            topics="メール",
            status="OK",
            topic="社内メール",
            sentiment="冷静"
        )
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
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=reply,
            category="メール送信",
            message_type="テキスト",
            topics="メール",
            status="OK",
            topic="社内メール",
            sentiment="冷静"
        )
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
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=reply,
            category="メール送信確認",
            message_type="テキスト",
            topics="社内メール",
            status="OK",
            topic="社内メール",
            sentiment="冷静"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    employee_info = read_employee_info()
    
    results = {
        "会話ログ": search_conversation_log(user_message, read_conversation_log()),
        "従業員情報": search_employee_info_by_keywords(user_message, employee_info),
        "取引先情報": search_partner_info_by_keywords(user_message, read_partner_info()),
        "会社情報": search_company_info_log(user_message, read_company_info()),
        "経験ログ": search_aiko_experience_log(user_message, read_aiko_experience_log()),
        "勤怠ログ": read_attendance_log(),
        "タスク情報": read_task_info()
    }
    log_if_all_searches_failed(results)

    reply = next((r for r in results.values() if r), None)
    if not reply:
        try:
            if contains_sensitive_info(user_message):
                combined = []
                for dataset in [employee_info, read_partner_info(), read_company_info(), read_aiko_experience_log()]:
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
        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="愛子",
            reply=short_reply,
            category="メール長文応答",
            message_type="テキスト",
            topics="メール",
            status="OK",
            topic="社内メール",
            sentiment="冷静"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return

    short_reply = reply[:100]
    log_aiko_reply(
        timestamp=timestamp,
        user_id=user_id,
        user_name=user_name,
        speaker="愛子",
        reply=short_reply,
        category="通常応答",
        message_type="テキスト",
        topics="通常応答",
        status="OK",
        topic="AI応答",
        sentiment="中立"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
