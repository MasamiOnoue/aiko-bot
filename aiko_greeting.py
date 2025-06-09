# aiko_greeting.py

from datetime import datetime, timedelta
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
from company_info_save import write_conversation_log

import pytz

# ユーザーごとの挨拶履歴を記録する辞書（時刻＋カテゴリ）
recent_greeting_users = {}

# JST取得関数
def now_jst():
    return datetime.now(pytz.timezone("Asia/Tokyo"))

# 最近3時間以内に同じカテゴリの挨拶があったかどうか
def has_recent_greeting(user_id, category):
    now = now_jst()
    record = recent_greeting_users.get(user_id)
    if record:
        last_time, last_category = record
        if (now - last_time).total_seconds() < 3 * 3600 and last_category == category:
            return True
    return False

# 挨拶の時刻とカテゴリを記録
def record_greeting_time(user_id, timestamp, category):
    recent_greeting_users[user_id] = (timestamp, category)

# 時間帯に応じた挨拶
def get_time_based_greeting(user_id=None):
    hour = now_jst().hour
    if 5 <= hour < 11:
        greeting = "おっはー"
    elif 11 <= hour < 18:
        greeting = "やっはろー"
    elif 18 <= hour < 23:
        greeting = "ばんわ～"
    else:
        greeting = "ねむ～"

    if user_id:
        name = get_user_callname_from_uid(user_id)
        if name and name != "不明":
            greeting += f"、{name}さん"
    return greeting

# 挨拶と認識される語を正規化
GREETING_KEYWORDS = [
    "おはよう", "おっはー", "おは", "おっは", "お早う", "お早うございます",
    "こんにちは", "こんばんは", "お疲れさま", "おつかれ"
]

def normalize_greeting(text):
    for word in GREETING_KEYWORDS:
        if word in text:
            return word[:3]  # カテゴリ例: "おは", "こん", "おつ"
    return None

# 挨拶以外の処理系（省略）
def is_attendance_related(message):
    return any(kw in message for kw in ["遅刻", "休み", "休暇", "出社", "在宅", "早退"])

def is_topic_changed(message):
    return any(kw in message for kw in ["やっぱり", "ちなみに", "ところで", "別件", "変更", "違う話"])

# ユーザー状態のダミー関数群（本番では他モジュールと連携）
def get_user_status(user_id):
    return {}

def update_user_status(user_id, step):
    pass

def reset_user_status(user_id):
    pass

def forward_message_to_others(api, from_name, message, uids):
    for uid in uids:
        api.push_message(uid, TextSendMessage(text=f"{from_name}さんより: {message}"))

from linebot.models import TextSendMessage

def get_user_name_for_sheet(user_id):
    return "不明"

def get_aiko_official_email():
    return "aiko@sun-name.com"

def fetch_latest_email():
    return "最新のメール本文です。"
