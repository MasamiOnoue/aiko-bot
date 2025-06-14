import os
import requests
import re
import logging
from aiko_greeting import now_jst

def log_aiko_reply(timestamp, user_id, user_name, speaker, reply, category, message_type, topics, status, topic, sentiment):
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S") 
        GCF_ENDPOINT = os.getenv("GCF_ENDPOINT")
        API_KEY = os.getenv("PRIVATE_API_KEY")

        if not GCF_ENDPOINT or not API_KEY:
            logging.error("❌ GCF_ENDPOINTまたはAPI_KEYが未設定")
            return

        url = f"{GCF_ENDPOINT.rstrip('/')}/write-conversation-log"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }

        payload = {
            "timestamp": timestamp,
            "user_id": user_id,
            "user_name": user_name,
            "speaker": speaker,
            "message": reply,
            "category": category,
            "message_type": message_type,
            "topic": topic,
            "status": status,
            "sentiment": sentiment
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            logging.info("✅ 会話ログ送信成功")
        else:
            logging.error(f"❌ 書き込み失敗: {response.status_code} - {response.text}")

    except Exception as e:
        logging.exception(f"❌ log_aiko_reply 例外: {e}")

def normalize_person_name(message):
    """
    メッセージから「さん」や「様」などの敬称を取り除く
    """
    for suffix in ["さん", "様", "くん", "ちゃん"]:
        if suffix in message:
            message = message.replace(suffix, "")
    return message

def remove_honorifics(text):
    for suffix in ["さん", "ちゃん", "くん"]:
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return text

def extract_keywords(text):
    cleaned = re.sub(r'[。、「」？?！!\n]', ' ', text)
    return [word for word in cleaned.split() if len(word) > 1]

def classify_attendance_type(qr_text: str) -> str:
    lowered = qr_text.lower()
    if "退勤" in lowered or "leave" in lowered:
        return "退勤"
    if "出勤" in lowered or "attend" in lowered:
        return "出勤"
    current_hour = now_jst().hour
    return "出勤" if current_hour < 14 else "退勤"

def count_keyword_matches(data_list, keywords):
    if not data_list:
        return 0
    headers = data_list[0].keys() if isinstance(data_list[0], dict) else []
    return sum(
        all(
            any(kw in str(v) for v in item.values()) or any(kw in h for h in headers)
            for kw in keywords
        ) for item in data_list
    )

def get_matching_entries(data_list, keywords, fields=None):
    """
    キーワードのいずれかが一致するデータエントリを抽出

    :param data_list: 辞書のリスト（例: 従業員一覧）
    :param keywords: 抽出に使うキーワードのリスト
    :param fields: 検索対象とするフィールド名のリスト（Noneなら全フィールド）
    :return: 条件にマッチする辞書のリスト
    """
    matches = []

    for entry in data_list:
        for keyword in keywords:
            target_fields = fields if fields else entry.keys()
            for field in target_fields:
                value = str(entry.get(field, ""))
                if keyword.lower() in value.lower():
                    matches.append(entry)
                    break  # 1つでも一致すれば追加して次の entry へ
            else:
                continue
            break

    return matches
