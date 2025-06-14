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
from aiko_helpers import log_aiko_reply
from attendance_logger import log_attendance_from_qr
from information_writer import write_attendance_log

MAX_HITS = 10
DEFAULT_USER_NAME = "不明"

def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id.strip().upper()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_name = get_user_callname_from_uid(user_id) or DEFAULT_USER_NAME
    logging.info(f"✅ user_name: {user_name}")
    registered_uids = load_all_user_ids()

    if isinstance(event.message, ImageMessage):
        return

    user_message = event.message.text.strip()
    category = classify_conversation_category(user_message)
    logging.info(f"🧠 カテゴリ分類: {category}")
    log_aiko_reply(timestamp, user_id, user_name, "ユーザー", user_message, category or "未分類", "テキスト", "未分類", "OK", "入力", "不明")

    greet_key = normalize_greeting(user_message)
    if greet_key and not has_recent_greeting(user_id, greet_key):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greet_key)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=greeting))
        return

    if user_id not in registered_uids:
        reply = "申し訳ありません。このサービスは社内専用です。"
        log_aiko_reply(timestamp, user_id, user_name, "愛子", reply, "権限エラー", "テキスト", "警告", "NG", "認証", "冷静")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    cleaned_message = remove_honorifics(user_message)
    keywords = extract_keywords(cleaned_message)
    logging.info(f"🔍 検索キーワード: {keywords}")

    sources = {
        "従業員情報": read_employee_info(),
        "会社情報": read_company_info(),
        "取引先情報": read_partner_info(),
        "会話ログ": read_conversation_log(),
        "経験ログ": read_aiko_experience_log(),
        "タスク情報": read_task_info(),
        "勤怠管理": read_attendance_log()
    }

    def get_score(k, v):
        weight = 2 if k in ["従業員情報", "取引先情報"] else 1
        return count_keyword_matches(v, keywords) * weight

    match_scores = {k: get_score(k, v) if isinstance(v, list) else 0 for k, v in sources.items()}
    priority_order = ["従業員情報", "会社情報", "取引先情報", "経験ログ", "タスク情報", "勤怠管理", "会話ログ"]
    best_source = max(priority_order, key=lambda k: match_scores[k])

    if match_scores[best_source] > 0:
        data = sources[best_source]
        matching_entries = [
            d for d in data if all(
                any(kw in str(v) for v in d.values()) or any(kw in h for h in d.keys())
                for kw in keywords
            )
        ]
        logging.info(f"🔎 最も一致したデータ: {matching_entries}")
        if matching_entries:
            result = matching_entries[0]

            target_callname = result.get("名前", "対象者")
            for e in sources["従業員情報"]:
                if e.get("名前") == result.get("名前"):
                    target_callname = e.get("愛子からの呼び名", target_callname)
                    break

            if "役職" in result:
                reply = f"{target_callname}は{result['役職']}です"
            else:
                summary_parts = []
                for key in ["名前", "役職", "部署", "会社名", "メール", "電話番号"]:
                    if key in result:
                        summary_parts.append(f"{key}:{result[key]}")
                summary_text = " / ".join(summary_parts)[:150]

                masked_text, mask_map = mask_sensitive_data(summary_text)
                prompt = f"以下の情報を自然な日本語にして、80文字以内に要約してください: {masked_text}"
                reply_masked = rephrase_with_masked_text(prompt)
                reply = unmask_sensitive_data(reply_masked, mask_map)
        else:
            reply = f"🔎 最も一致したのは「{best_source}」ですが、関連データの表示に失敗しました。"
    else:
        if category == "質問":
            try:
                reply = ask_openai_general_question(user_id, user_message)
            except Exception as e:
                reply = f"なんですか？（質問の処理に失敗しました: {e}）"
        else:
            recent_logs = get_recent_conversation_log(user_id, limit=20)
            prompt = generate_contextual_reply_from_context(user_id, user_message, recent_logs)
            try:
                reply = client.chat(prompt)
            except Exception as e:
                reply = f"申し訳ありません。現在応答できません（{e}）"

    if len(reply) > 80:
        update_user_status(user_id, 200)
        update_user_status(user_id + "_fulltext", reply)
        short_reply = "もっと情報がありますがLINEでは送れないのでメールで送りますか？"
        log_aiko_reply(timestamp, user_id, user_name, "愛子", short_reply, "メール長文応答", "テキスト", "メール", "OK", "社内メール", "冷静")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return

    short_reply = reply[:100]
    log_aiko_reply(timestamp, user_id, user_name, "愛子", short_reply, "通常応答", "テキスト", "通常応答", "OK", "AI応答", "中立")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
