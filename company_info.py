# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
#from company_info_load import get_google_sheets_service
from openai_client import client  # OpenAIクライアントを共通管理
from googleapiclient.discovery import build
from google.oauth2 import service_account

# === 従業員情報検索 ===
def search_employee_info_by_keywords(user_message, employee_info_list):
    alias_dict = {
        "おきく": "菊田京子", "まさみ": "政美", "かおり": "香織",
        "こうちゃん": "孝一", "考ちゃん": "孝一", "工場長": "折戸",
    }
    attributes = {
        "役職": 4, "入社年": 5, "生年月日": 6, "性別": 7,
        "メールアドレス": 8, "個人メールアドレス": 9, "携帯電話番号": 10,
        "自宅電話": 11, "住所": 12, "郵便番号": 13, "緊急連絡先": 14,
        "ペット情報": 15, "性格": 16, "家族構成": 17
    }

    user_message = user_message.replace("ちゃん", "さん").replace("君", "さん").replace("くん", "さん")
    for alias, real_name in alias_dict.items():
        if alias in user_message:
            user_message = user_message.replace(alias, real_name)

    for row in employee_info_list:
        if len(row) < 18:
            continue
        name = row[3]
        if name and (name in user_message or f"{name}さん" in user_message):
            for keyword, index in attributes.items():
                if keyword in user_message:
                    value = row[index].strip() if index < len(row) and row[index].strip() else "不明"
                    return f"{name}さんの{keyword}は {value} です。"

    logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return "申し訳ありませんが、該当の情報が見つかりませんでした。"

# === 会話分類 ===
def classify_conversation_category(message):
    categories = {"重要", "日常会話", "あいさつ", "業務情報", "その他"}
    prompt = (
        "以下の会話内容を、次のいずれかのカテゴリで1単語だけで分類してください："
        "「重要」「日常会話」「あいさつ」「業務情報」「その他」。\n\n"
        f"会話内容:\n{message}\n\nカテゴリ名だけを返してください。"
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
        if category not in categories:
            logging.warning(f"⚠️ 不明なカテゴリ: {category}")
            return "未分類"
        return category
    except Exception as e:
        logging.error(f"❌ カテゴリ分類失敗: {e}")
        return "未分類"

def load_all_user_ids(sheet_service=None):
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID2")  # 従業員情報シートのID

    if sheet_service is None:
        creds = service_account.Credentials.from_service_account_file(
            "aiko-bot-log-2fc8779943bc.json",  # 適切なJSONファイル
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheet_service = build("sheets", "v4", credentials=creds).spreadsheets()

    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="従業員情報!L2:L"  # ← L列がUIDならOK
        ).execute()
        values = result.get("values", [])

        return [
            row[0].strip()
            for row in values
            if row and row[0].strip().startswith("U") and len(row[0].strip()) >= 10
        ]
    except Exception as e:
        logging.error(f"❌ UID読み込みエラー: {e}")
        return []


