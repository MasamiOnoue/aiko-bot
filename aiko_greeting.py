# aiko_greeting.py

from datetime import datetime, timedelta
from linebot import LineBotApi
from linebot.models import TextSendMessage
import pytz
import re

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

# 同じ語が2回繰り返されていたら1回だけに
def clean_user_name(name: str) -> str:
    name = re.sub(r"(.+?)\1", r"\1", name)

    # 「さんさん」や「君君」などの繰り返し接尾辞を防ぐ
    name = re.sub(r"(さん|君|くん|ちゃん)\1", r"\1", name)

    return name

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
            cleaned_name = clean_user_name(name)
            greeting += f"、{cleaned_name}"
    return greeting

# 挨拶と認識される語を正規化
GREETING_KEYWORDS = [
    # 朝の挨拶系
    "おはよう", "おっはー", "おは", "おっは", "お早う", "お早うございます",
    "おはよー", "おはよ", "おっは", "オハヨ", "オハヨー", "ohayo", "oha",  # ゆる表記
    
    # 昼の挨拶系
    "こんにちは", "こんにちわ", "こんちわ", "こんちは", "ちわーす", "ちわっす", "ちわっ", "チワ", "konchiwa", "konnichiwa",
    
    # 夜の挨拶系
    "こんばんは", "こんばんわ", "ばんわ", "ばんは", "コンバンハ", "konbanwa",

    # お疲れ系
    "お疲れ", "おつかれ", "おつかれさま", "お疲れ様", "おつー", "おつ", "乙", "オツ", "おつおつ", "おつでした", "otsukare",

    # カジュアル挨拶
    "やあ", "ハロー", "hello", "hi", "やっほー", "やっはろー", "よっ", "ども", "どうも", "ちわっす"
]

def normalize_greeting(text):
    for word in GREETING_KEYWORDS:
        if word in text:
            return word[:3]  # カテゴリ例: "おは", "こん", "おつ"
    if "お疲" in text or "おつかれ" in text:
        return "おつ"
    return None

# 雑談とみなすキーワード・パターンを抽出
def is_smalltalk(message):
    smalltalk_patterns = [
        r"寝(てた|てる|たの)", r"起き(た|てる|てた)", r"元気", r"どう(して|だった)", r"なにしてる", r"なにしてた",
        r"暇", r"ひま", r"調子", r"疲れ", r"眠い", r"眠かった", r"お腹すいた", r"ねむい", r"さみしい", r"孤独"
    ]
    return any(re.search(pat, message.lower()) for pat in smalltalk_patterns)
    
# 挨拶以外の処理系（省略）
def is_attendance_related(message):
    #return any(kw in message for kw in ["遅刻", "休み", "休暇", "出社", "在宅", "早退", "遅れます", "遅れる", "遅れそう", "遅くなります", "遅れて", "休んで"])
    patterns = [
        r"遅(刻|れ).*",             # 遅刻、遅れます、遅れて etc.
        r"休(み|暇)",               # 休み、休暇
        r"有給", r"欠勤",            # 有給、欠勤
        r"(出社|在宅|テレワーク)",    # 出社、在宅、テレワーク
        r"(早退|外出|直行|直帰)",     # 早退、外出など
        r"(午前|午後)?半休",         # 午前半休、午後半休、半休
        r"午後休",                  # 午後休
    ]
    return any(re.search(pat, message) for pat in patterns)
    
def is_topic_changed(message):
    return any(kw in message for kw in ["やっぱり", "ちなみに", "ところで", "別件", "変更", "違う話"])

# ユーザー状態のダミー関数群（本番では他モジュールと連携）
def get_user_status(user_id):
    return {}  # 本番運用時には外部ステータス管理モジュールで上書きされます

def update_user_status(user_id, step):
    pass

def reset_user_status(user_id):
    pass

def forward_message_to_others(api: LineBotApi, from_name: str, message: str, uids: list):
    for uid in uids:
        api.push_message(uid, TextSendMessage(text=f"{from_name}より: {message}"))

def get_user_name_for_sheet(user_id):
    return "不明"

def get_aiko_official_email():
    return "aiko@sun-name.com"

def fetch_latest_email():
    return "最新のメール本文です。"
