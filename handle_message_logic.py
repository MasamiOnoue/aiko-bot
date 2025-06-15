# handle_message_logic.py  LINEメッセージを受け取ったときのメイン処理

import os
import logging
import re
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
    read_attendance_log,
    read_recent_conversation_log
)
from aiko_mailer import (
    draft_email_for_user, send_email_with_confirmation, get_user_email_from_uid, fetch_latest_email
)
from mask_word import (
    contains_sensitive_info, mask_sensitive_data,
    unmask_sensitive_data, rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply_from_context
from openai_client import client, ask_openai_general_question
from aiko_helpers import (
    log_aiko_reply, get_matching_entries, normalize_person_name,
    remove_honorifics, extract_keywords, classify_attendance_type, count_keyword_matches,
    FIELD_MAPPING, detect_requested_field, ensure_list_of_dicts
)
from attendance_logger import log_attendance_from_qr
from information_writer import write_attendance_log

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id.strip().upper()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    employee_info_raw = read_employee_info()
    logging.info(f"🐞 デバッグ: employee_info_raw = {employee_info_raw}")
    employee_info_list = ensure_list_of_dicts(employee_info_raw, label="従業員")
    logging.info(f"🐞 デバッグ: employee_info_list = {employee_info_list}")

    user_name = get_user_callname_from_uid(user_id, employee_info_list) or DEFAULT_USER_NAME
    logging.info(f"✅ user_name: {user_name}")
    registered_uids = load_all_user_ids()

    if isinstance(event.message, ImageMessage):
        return

    user_message = event.message.text.strip()
    logging.info(f"💬 受信メッセージ: {user_message}")
    category = classify_conversation_category(user_message)
    logging.info(f"🧠 カテゴリ分類: {category}")
    log_aiko_reply(timestamp, user_id, user_name, "ユーザー", user_message, category or "未分類", "テキスト", "未分類", "OK", "入力", "不明")

    greet_key = normalize_greeting(user_message)
    if greet_key and not has_recent_greeting(user_id, greet_key):
        try:
            prompt = f"ユーザーから『{user_message}』という挨拶がありました。愛子らしく挨拶を返してください。"
            logging.info(f"🗣️ OpenAI送信プロンプト（挨拶）: {prompt}")
            reply = client.chat(prompt)
            logging.info(f"📥 OpenAI応答: {reply}")
        except Exception:
            reply = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greet_key)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if user_id not in registered_uids:
        reply = "申し訳ありません。このサービスは社内専用です。"
        log_aiko_reply(timestamp, user_id, user_name, "愛子", reply, "権限エラー", "テキスト", "警告", "NG", "認証", "冷静")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if category in ["挨拶", "雑談", "その他", "ニュース・時事"]:
        logging.info(f"🗣️ OpenAIへ送信するユーザーメッセージ: {user_message}")
        recent_logs = read_recent_conversation_log(user_id, limit=20)
        prompt = generate_contextual_reply_from_context(user_id, user_message, recent_logs)
        logging.info(f"📤 OpenAI送信プロンプト: {prompt}")
        try:
            reply = client.chat(prompt)
            logging.info(f"📥 OpenAI応答: {reply}")
        except Exception as e:
            reply = f"申し訳ありません。現在応答できません（{e}）"
        short_reply = reply[:100]
        log_aiko_reply(timestamp, user_id, user_name, "愛子", short_reply, "通常応答", "テキスト", category, "OK", "AI応答", "中立")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return

    logging.info("🔎 内部API検索に進みます（業務情報カテゴリ）")
    logging.info(f"🗣️ 内部API検索用ユーザーメッセージ: {user_message}")
    cleaned_message = normalize_person_name(user_message)
    keywords = extract_keywords(cleaned_message)
    logging.info(f"🔍 検索キーワード: {keywords}")

    if employee_info_list and isinstance(employee_info_list, list) and isinstance(employee_info_list[0], dict):
        employee_matches = get_matching_entries(keywords, employee_info_list, ["名前", "呼ばれ方", "名前の読み"])
        if employee_matches:
            matched = employee_matches[0]
            name = matched.get("名前", "不明")
            field = detect_requested_field(user_message)
            value = matched.get(field, "不明")
            reply = f"{name}さんの{field}は{value}です。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
    else:
        logging.warning("⚠️ 従業員データが空または形式不正のため、人物情報の検索をスキップします。")

    sources = {
        "会社情報": read_company_info(),
        "取引先情報": read_partner_info(),
        "経験ログ": read_aiko_experience_log(),
        "タスク情報": read_task_info(),
        "勤怠管理": read_attendance_log()
    }

    match_any = False
    for name, data in sources.items():
        if isinstance(data, list):
            count = count_keyword_matches(data, keywords)
            logging.info(f"🔢 {name} の一致件数: {count}")
            if count > 0:
                match_any = True

    if not match_any:
        logging.info("❗検索結果が全データで0件でした。OpenAIに処理を委譲します。")
        logging.info(f"🗣️ OpenAIへ送信するユーザーメッセージ: {user_message}")
        recent_logs = read_recent_conversation_log(user_id, limit=20)
        prompt = generate_contextual_reply_from_context(user_id, user_message, recent_logs)
        logging.info(f"📤 OpenAI送信プロンプト: {prompt}")
        try:
            reply = ask_openai_general_question(user_id, user_message)
            logging.info(f"📥 OpenAI応答: {reply}")
        except Exception as e:
            reply = f"なんですか？（質問の処理に失敗しました: {e}）"
        short_reply = reply[:100]
        log_aiko_reply(timestamp, user_id, user_name, "愛子", short_reply, "OpenAI応答", "テキスト", category, "OK", "AI応答", "中立")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return
