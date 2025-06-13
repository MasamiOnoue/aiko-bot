# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
from openai_client import client  # OpenAIクライアントを共通管理
import requests

# === 従業員情報検索 ===
def search_employee_info_by_keywords(user_message, employee_info_list):
    alias_dict = {
        "おきく": "菊田京子", "まさみ": "政美", "かおり": "香織",
        "こうちゃん": "孝一", "考ちゃん": "孝一", "工場長": "折戸",
    }
    # 属性名とキーの対応（dict対応）
    attributes = {
        "役職": "役職", "入社年": "入社年", "生年月日": "生年月日", "性別": "性別",
        "メールアドレス": "メールアドレス", "個人メールアドレス": "個人メールアドレス",
        "携帯電話番号": "携帯電話番号", "自宅電話": "自宅電話", "住所": "住所",
        "郵便番号": "郵便番号", "緊急連絡先": "緊急連絡先", "ペット情報": "ペット情報",
        "性格": "性格", "家族構成": "家族構成"
    }

    # 整形
    user_message = user_message.replace("ちゃん", "さん").replace("君", "さん").replace("くん", "さん")
    for alias, real_name in alias_dict.items():
        if alias in user_message:
            user_message = user_message.replace(alias, real_name)

    for record in employee_info_list:
        name = record.get("氏名", "")
        if name and (name in user_message or f"{name}さん" in user_message):
            for keyword, field in attributes.items():
                if keyword in user_message:
                    value = record.get(field, "").strip() or "不明"
                    return f"{name}さんの{keyword}は {value} です。"

    logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return "申し訳ありませんが、該当の情報が見つかりませんでした。"
    
def load_all_user_ids():
    logging.info(f"📡 現在の GCF_ENDPOINT: {os.getenv('GCF_ENDPOINT')}")
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "x-api-key": api_key
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        result = [
            row[11].strip().upper()
            for row in values
            if len(row) > 11 and row[11] and row[11].strip().startswith("U")
        ]

        logging.info(f"✅ 読み込んだUID一覧: {result}")
        return result
    except Exception as e:
        logging.error(f"❌ UID読み込みエラー: {e}")
        return []

def get_user_callname_from_uid(user_id):
    logging.info(f"📥 従業員情報レスポンス: {response.text}")
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "x-api-key": api_key
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        for row in values:
            if len(row) >= 12 and row[11].strip().upper() == user_id.strip().upper():
                return row[3].strip() if row[3].strip() else row[2].strip()  # 呼ばれ方 or 名前
        return "不明な方"
    except Exception as e:
        logging.error(f"❌ 呼び名取得エラー: {e}")
        return "エラー"
