# aiko_greeting.py

from datetime import datetime, timedelta
import pytz

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
