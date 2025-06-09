# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI
from company_info_load import get_google_sheets_service

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')

def search_employee_info_by_keywords(user_message, employee_info_list):
    # 愛称辞書を定義
    alias_dict = {
        "おきく": "菊田京子",
        "まさみ": "政美",
        "かおり": "香織",
        "こうちゃん": "孝一",
        "考ちゃん": "孝一",
        "工場長": "折戸",
        # 必要に応じて追加
    }
    attributes = {
        "役職": 4,
        "入社年": 5,
        "生年月日": 6,
        "性別": 7,
        "メールアドレス": 8,
        "個人メールアドレス": 9,
        "携帯電話番号": 10,
        "自宅電話": 11,
        "住所": 12,
        "郵便番号": 13,
        "緊急連絡先": 14,
        "ペット情報": 15,
        "性格": 16,
        "家族構成": 17
    }

    found = False
    user_message = user_message.replace("ちゃん", "さん").replace("君", "さん").replace("くん", "さん")
    # 愛称が含まれていれば正式名に置換
    for alias, real_name in alias_dict.items():
        if alias in user_message:
            user_message = user_message.replace(alias, real_name)  # ニックネーム対応

    for row in employee_info_list:
        if len(row) < 18:
            continue
        name = row[3]
        if not name:
            continue

        # フルネーム一致または「さん」付き名前一致
        if name in user_message or f"{name}さん" in user_message:
            for keyword, index in attributes.items():
                if keyword in user_message:
                    value = row[index] if index < len(row) and row[index].strip() != "" else "不明"
                    found = True
                    return f"{name}さんの{keyword}は {value} です。"

    if not found:
        logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return "申し訳ありませんが、該当の情報が見つかりませんでした。"

############## 補助系 ###########################

def classify_conversation_category(message):
    """
    OpenAIを使って会話内容をカテゴリ分類する。
    候補カテゴリ：「重要」「日常会話」「あいさつ」「業務情報」「その他」
    """
    prompt = (
        "以下の会話内容を、次のいずれかのカテゴリで1単語だけで分類してください："
        "「重要」「日常会話」「あいさつ」「業務情報」「その他」。\n\n"
        f"会話内容:\n{message}\n\n"
        "カテゴリ名だけを返してください。"
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
        return category
    except Exception as e:
        logging.error(f"❌ カテゴリ分類失敗: {e}")
        return "未分類"
