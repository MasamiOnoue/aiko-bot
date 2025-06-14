# handle_message_logic.py  LINEメッセージを受け取ったときのメイン処理

import os
import logging
from datetime import datetime
from linebot.models import TextSendMessage, ImageMessage
from PIL import Image
import tempfile

try:
    import pytesseract
except ImportError:
    pytesseract = None
    print("⚠️ pytesseract is not available in this environment.")

from aiko_greeting import (
    now_jst, get_time_based_greeting, is_attendance_related, is_topic_changed,
    get_user_status, update_user_status, reset_user_status, forward_message_to_others,
    has_recent_greeting, record_greeting_time, normalize_greeting, classify_conversation_category
)
from company_info import (
    search_employee_info_by_keywords,
    search_partner_info_by_keywords, 
    search_company_info_log,   
    search_experience_log,      
    search_conversation_log,    
    log_if_all_searches_failed, 
    get_user_callname_from_uid,
    load_all_user_ids
)
from information_reader import (
    get_employee_info,
    get_partner_info, 
    get_company_info,  
    get_conversation_log, 
    get_experience_log,
    read_task_info,
    read_attendance_log
)
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
from attendance_logger import log_attendance_from_qr
from information_writer import write_attendance_log

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

# 検索前に敬称を除去するヘルパー関数
def remove_honorifics(text):
    for suffix in ["さん", "ちゃん", "くん"]:
        text = text.replace(suffix, "")
    return text

def classify_attendance_type(qr_text: str) -> str:
    """
    QRテキストから出勤/退勤を自動判別する
    """
    lowered = qr_text.lower()
    if "退勤" in lowered or "leave" in lowered:
        return "退勤"
    if "出勤" in lowered or "attend" in lowered:
        return "出勤"
    current_hour = now_jst().hour
    return "出勤" if current_hour < 14 else "退勤"

def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id.strip().upper()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_name = get_user_callname_from_uid(user_id) or DEFAULT_USER_NAME
    logging.info(f"✅ user_name: {user_name}")
    registered_uids = load_all_user_ids()

    if isinstance(event.message, ImageMessage):
        user_message = f"✅ {user_name}さんが打刻しました"

        log_aiko_reply(
            timestamp=timestamp,
            user_id=user_id,
            user_name=user_name,
            speaker="ユーザー",
            reply=user_message,
            category="画像",
            message_type="画像",
            topics="QRコード",
            status="OK",
            topic="出退勤",
            sentiment="中立"
        )
        try:
            message_content = line_bot_api.get_message_content(event.message.id)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                for chunk in message_content.iter_content():
                    tf.write(chunk)
                temp_image_path = tf.name

            if pytesseract and Image:
                img = Image.open(temp_image_path)
                qr_text = pytesseract.image_to_string(img, lang='jpn').strip()
                spreadsheet_id = os.getenv("SPREADSHEET_ID7")
                if not spreadsheet_id:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="SPREADSHEET_ID7 が設定されていません。"))
                    return
                attendance_type = classify_attendance_type(qr_text)
                logging.info(f"🔍 QR内容: {qr_text} => {attendance_type}")
                result = log_attendance_from_qr(user_id, qr_text, spreadsheet_id, attendance_type)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
            else:
                logging.warning("❌ OCR機能は現在の環境では利用できません。")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="OCR機能が使えない環境です。"))
        except Exception as e:
            logging.error(f"QRコード画像処理エラー: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="QRコードの読み取りに失敗しました。別の画像をお試しください。"))
        return

    user_message = event.message.text.strip()
    log_aiko_reply(
        timestamp=timestamp,
        user_id=user_id,
        user_name=user_name,
        speaker="ユーザー",
        reply=user_message,
        category="入力",
        message_type="テキスト",
        topics="未分類",
        status="OK",
        topic="入力",
        sentiment="不明"
    )

    greet_key = normalize_greeting(user_message)
    if greet_key and not has_recent_greeting(user_id, greet_key):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greet_key)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=greeting))
        return

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

    employee_info = get_employee_info()
    cleaned_message = remove_honorifics(user_message)
    results = {
        "会話ログ": search_conversation_log(cleaned_message, get_conversation_log()),
        "従業員情報": search_employee_info_by_keywords(cleaned_message, employee_info),
        "取引先情報": search_partner_info_by_keywords(cleaned_message, get_partner_info()),
        "会社情報": search_company_info_log(cleaned_message, get_company_info()),
        "経験ログ": search_experience_log(cleaned_message, get_experience_log()),
        "タスク情報": read_task_info(),
        "勤怠管理": read_attendance_log()
    }
    log_if_all_searches_failed(results)

    reply = next((r for r in results.values() if r), None)
    if not reply:
        try:
            system_instruction = "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示し、LINE返信は100文字以内にまとめてください。"
            if contains_sensitive_info(user_message):
                masked_input, mask_map = mask_sensitive_data(user_message)
                prompt = f"{system_instruction}\n\nユーザーの入力: {masked_input}"
                reply_masked = rephrase_with_masked_text(prompt)
                reply = unmask_sensitive_data(reply_masked, mask_map)
            else:
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
