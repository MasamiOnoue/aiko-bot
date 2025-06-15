# aiko_helpers.py

import os
import re
import requests
import logging
from aiko_greeting import now_jst
from information_reader import read_employee_info

def log_aiko_reply(user_id, user_name, speaker, reply, category, message_type, topics, status, topic, sentiment, source):  # timestamp 引数削除済み
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")  # 現在時刻を使用（引数では受け取らない）
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
            "sentiment": sentiment,
            "source": source
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
    return remove_honorifics(message)

def remove_honorifics(text):
    for suffix in ["さん", "様", "くん", "ちゃん"]:
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
        any(
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
                    break
            else:
                continue
            break

    return matches

def build_field_mapping():
    field_mapping = {}

    employee_info_list = read_employee_info()
    if employee_info_list:
        headers = employee_info_list[0].keys()
        for header in headers:
            field_mapping[header] = [header]

    field_mapping.update({
        "役職": field_mapping.get("役職", []) + ["ポジション"],
        "入社年": field_mapping.get("入社年", []) + ["入社"],
        "住所": field_mapping.get("住所", []) + ["住まい", "どこ住み"],
        "電話番号": field_mapping.get("電話番号", []) + ["電話", "携帯", "連絡先"],
        "メールアドレス": field_mapping.get("メールアドレス", []) + ["メール", "アドレス", "e-mail"],
        "性別": field_mapping.get("性別", []) + ["男女"],
        "緊急連絡先": field_mapping.get("緊急連絡先", []) + ["緊急", "家族"],
        "性格": field_mapping.get("性格", []) + ["タイプ"],
        "ペット情報": field_mapping.get("ペット情報", []) + ["動物"]
    })

    return field_mapping

FIELD_MAPPING = build_field_mapping()

def detect_requested_field(text: str) -> str:
    for field, keywords in FIELD_MAPPING.items():
        for kw in keywords:
            if kw in text:
                return field
    return "役職"
