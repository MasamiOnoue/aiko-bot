# aiko_greeting.py

import pytz
import logging
import re
import requests
from openai_client import client
from datetime import datetime, timedelta
from linebot import LineBotApi
from linebot.models import TextSendMessage
from company_info import get_user_callname_from_uid

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
            if any(name.endswith(suffix) for suffix in ["さん", "様", "くん", "ちゃん"]):
                greeting += f"、{name}"
            else:
                greeting += f"、{name}さん"
    return greeting

# 現在の天気情報を取得（Open-Meteo API使用・東京都想定）
def get_current_weather():
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 35.6812,
                "longitude": 139.7671,
                "current_weather": True
            },
            timeout=5
        )
        data = response.json()
        weather = data.get("current_weather", {})
        temp = weather.get("temperature")
        condition = weather.get("weathercode")
        description = f"現在の気温は約{temp}℃、天気コードは{condition}です。"
        return description
    except Exception as e:
        logging.warning(f"天気情報取得失敗: {e}")
        return "天気情報の取得に失敗しました。"

# OpenAIへ直接質問する（業務外の質問対応）
def ask_openai_general_question(message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは親切で知識豊富なAIアシスタントです。"},
                {"role": "user", "content": message}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"OpenAIへの一般質問失敗: {e}")
        return "すみません、質問の処理中に問題が発生しました。"

# 挨拶と認識される語を正規化（長い語順にソート）
GREETING_KEYWORDS = sorted([
    "おはよう", "おっはー", "おは", "おっは", "お早う", "お早うございます",
    "こんにちは", "こんばんは", "お疲れさま", "おつかれ"
], key=lambda x: -len(x))

def normalize_greeting(text):
    for word in GREETING_KEYWORDS:
        if word in text:
            return word[:3]
    return None

# ノイズ検知関数（意味不明な文字列を検出）
def is_gibberish(text):
    if len(text) < 3:
        return True
    valid_chars = re.findall(r'[ぁ-んァ-ン一-龯a-zA-Z0-9ａ-ｚＡ-Ｚ０-９]', text)
    ratio = len(valid_chars) / len(text)
    return ratio < 0.4

# 業務系キーワードによる強制分類フィルター
def contains_work_keywords(message):
    work_keywords = ["役職", "出勤", "退勤", "作業", "工程", "指示", "会議", "勤怠", "報告"]
    return any(kw in message for kw in work_keywords)

# 挨拶以外の処理系（省略）
def is_attendance_related(message):
    return any(kw in message for kw in ["遅刻", "休み", "休暇", "出社", "在宅", "早退"])

def is_topic_changed(message):
    return any(kw in message for kw in ["やっぱり", "ちなみに", "ところで", "別件", "変更", "違う話"])

# ユーザー状態のダミー関数群
def get_user_status(user_id):
    return {}

def update_user_status(user_id, step):
    pass

def reset_user_status(user_id):
    pass

def forward_message_to_others(api: LineBotApi, from_name: str, message: str, uids: list):
    for uid in uids:
        api.push_message(uid, TextSendMessage(text=f"{from_name}さんより: {message}"))

def get_user_name_for_sheet(user_id):
    return "不明"

# === 会話分類 ===
def classify_conversation_category(message):
    if is_gibberish(message):
        logging.info(f"🌀 ノイズ判定: {message}")
        return "その他"
    if contains_work_keywords(message):
        logging.info(f"🔍 業務キーワード分類: {message}")
        return "業務情報"

    categories = {
        "あいさつ", "業務情報", "質問", "雑談", "読み方", "地理", "人間関係",
        "人物情報", "趣味・関心", "体調・健康", "スケジュール", "感謝・謝罪",
        "食事・栄養", "天気", "ニュース・時事", "交通・移動", "買い物・物品",
        "金銭・支払い", "意見・提案", "指示・依頼", "感情・気持ち", "その他"
    }
    prompt = (
        "以下の文章を、次のカテゴリのうち最も適切なもの1つに分類してください："
        "「あいさつ」「業務情報」「質問」「雑談」「読み方」「地理」「人間関係」"
        "「人物情報」「趣味・関心」「体調・健康」「スケジュール」「感謝・謝罪」"
        "「食事・栄養」「天気」「ニュース・時事」「交通・移動」「買い物・物品」"
        "「金銭・支払い」「意見・提案」「指示・依頼」「感情・気持ち」「その他」\n\n"
        "■カテゴリの定義：\n...（省略）..."
        f"文章:\n「{message}」\n\n"
        "カテゴリ名だけを返してください"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは優秀な会話分類AIです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,
            temperature=0
        )
        category = response.choices[0].message.content.strip()
        if not category or category not in categories:
            logging.warning(f"⚠️ 不明なカテゴリ: '{category}' → {message}")
            return "その他"
        logging.info(f"✅ 分類結果: {category} ← {message}")
        return category
    except Exception as e:
        logging.error(f"❌ カテゴリ分類失敗: {e}")
        return "その他"
