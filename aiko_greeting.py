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
                "latitude": 35.6812,  # 東京駅の緯度
                "longitude": 139.7671,  # 東京駅の経度
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
        return "その他"

    # 対策3: 業務キーワードが含まれる場合は強制的に業務情報として扱う
    if contains_work_keywords(message):
        return "業務情報"

    categories = {
        "あいさつ", "業務情報", "質問", "雑談", "読み方", "地理", "人間関係",
        "人物情報", "趣味・関心", "体調・健康", "スケジュール", "感謝・謝罪",
        "食事・栄養", "天気", "ニュース・時事", "交通・移動", "買い物・物品", "金銭・支払い", "意見・提案", "指示・依頼", "感情・気持ち", "その他"
    }
    prompt = (
        "以下の文章を、次のカテゴリのうち最も適切なもの1つに分類してください："
        "「あいさつ」「業務情報」「質問」「雑談」「読み方」「地理」「人間関係」"
        "「人物情報」「趣味・関心」「体調・健康」「スケジュール」「感謝・謝罪」"
        "「食事・栄養」「天気」「ニュース・時事」「交通・移動」「買い物・物品」"
        "「金銭・支払い」「意見・提案」「指示・依頼」「感情・気持ち」「その他」\n\n"
        "■カテゴリの定義：\n"
        "・あいさつ：おはよう、こんにちは等の礼儀的な言葉\n"
        "・業務情報：勤怠・作業・報告・会議など業務に関する内容\n"
        "・質問：定義や数値、事実確認などの問い\n"
        "・雑談：世間話や日常の軽い会話\n"
        "・読み方：漢字や名前の読みの確認\n"
        "・地理：地名や都道府県に関する内容\n"
        "・人間関係：家族や職場の人間関係に関する話\n"
        "・人物情報：性格・特徴・雰囲気など人に関する内容\n"
        "・趣味・関心：好きなことや興味関心に関する話\n"
        "・体調・健康：病気・疲れ・けがなど身体状態の話\n"
        "・スケジュール：予定・日程・時間に関する話\n"
        "・感謝・謝罪：ありがとう・ごめんなさい等の感情表現\n"
        "・食事・栄養：ご飯・飲み物・栄養などの話題\n"
        "・天気：天候・気温・天気予報などに関する内容\n"
        "・ニュース・時事：最近の出来事や世間の話題\n"
        "・交通・移動：通勤・交通手段・移動に関する話題\n"
        "・買い物・物品：商品・購入・在庫・注文などに関する話題\n"
        "・金銭・支払い：料金・給料・支払い・価格に関する内容\n"
        "・意見・提案：考え・提案・改善案など\n"
        "・指示・依頼：何かしてほしい・してもらいたい等の依頼\n"
        "・感情・気持ち：うれしい・悲しい・不安・怒りなど感情の表現\n"
        "・その他：上記に該当しない特殊な話題\n\n"
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
        if not category:
            logging.warning("⚠️ GPTから空の応答を受信しました。")
            return "その他"
        if category not in categories:
            logging.warning(f"⚠️ 不明なカテゴリ: {category}")
            return "その他"

        # 対策1・2: 業務に関係しそうなカテゴリも業務検索対象とみなせるようログ出力
        if category in {"業務情報", "質問", "人物情報", "雑談"}:
            logging.info(f"🔍 検索対象カテゴリとして処理: {category}")

        return category
    except Exception as e:
        logging.error(f"❌ カテゴリ分類失敗: {e}")
        return "その他"
