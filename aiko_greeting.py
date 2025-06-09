# aiko_greeting.py

from datetime import datetime, timedelta
import pytz
import re
from company_info import get_user_callname_from_uid, get_employee_info, get_google_sheets_service
from linebot import LineBotApi
from linebot.models import TextSendMessage
import os

# JST取得関数
def now_jst():
    return datetime.now(pytz.timezone("Asia/Tokyo"))

# ユーザーごとの挨拶履歴を記録する辞書
recent_greeting_users = {}

# ユーザーの挨拶時刻を記録
def record_greeting_time(user_id, timestamp):
    recent_greeting_users[user_id] = timestamp

# 最近3時間以内に挨拶済みかどうかを判定
def has_recent_greeting(user_id):
    now = now_jst()
    last_greet_time = recent_greeting_users.get(user_id)
    if last_greet_time and (now - last_greet_time) < timedelta(hours=3):
        return True
    return False

# 時間帯による挨拶関数
def get_time_based_greeting():
    current_time = now_jst()
    hour = current_time.hour
    if 5 <= hour < 10:
        return "おっはー。"
    elif 10 <= hour < 18:
        return "やっはろー。"
    elif 18 <= hour < 23:
        return "おっつ〜。"
    else:
        return "ねむねむ。"

# 出社・遅刻関連メッセージの確認ループ管理
user_status_flags = {}

# メッセージが出社・遅刻関連かを判定
def is_attendance_related(text):
    keywords = ["行きます", "出社します", "遅れます"]
    return any(word in text for word in keywords)

# 話題が変わったかどうかを判定（単純なキーワード除外）
def is_topic_changed(text):
    if text in ["はい", "いいえ"]:
        return False
    return not is_attendance_related(text)

# フラグ管理処理（初期化・取得・更新）
def get_user_status(user_id):
    return user_status_flags.get(user_id, {"step": 0, "timestamp": now_jst()})

def reset_user_status(user_id):
    if user_id in user_status_flags:
        del user_status_flags[user_id]

def update_user_status(user_id, step):
    user_status_flags[user_id] = {"step": step, "timestamp": now_jst()}

# 2時間経過したら自動リセット（外部スケジューリング想定）
def reset_expired_statuses():
    now = now_jst()
    expired = [uid for uid, data in user_status_flags.items() if (now - data["timestamp"]) > timedelta(hours=2)]
    for uid in expired:
        del user_status_flags[uid]

# ユーザーIDから名前へ変換（J列: 担当者に使用）
def get_user_name_for_sheet(user_id):
    sheet_service = get_google_sheets_service()
    employees = get_employee_info(sheet_service)
    for emp in employees:
        if len(emp) >= 12 and emp[11] == user_id:
            return emp[3]  # D列: 愛子からの呼ばれ方
    return get_user_callname_from_uid(user_id) or user_id

# LINEメッセージ転送機能（他の社員へ）
def forward_message_to_others(line_bot_api: LineBotApi, sender_name: str, message: str, recipients: list):
    intro = f"{sender_name}さんから伝言です"
    full_message = f"{intro}\n{message}"
    for user_id in recipients:
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=full_message))
        except Exception as e:
            print(f"❌ 転送失敗: {user_id}: {e}")
