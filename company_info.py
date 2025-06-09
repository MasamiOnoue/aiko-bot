# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')

# Google Sheets 接続サービスの取得
def get_google_sheets_service():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'aiko-bot-log-cfbf23e039fd.json')
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets().values()
    except Exception as e:
        logging.error(f"❌ Google Sheets認証エラー: {e}")
        return None

...（中略、他の関数はそのまま）...

#キーワードで従業員の情報を検索する
def search_employee_info_by_keywords(user_message, employee_info_list):
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
    for row in employee_info_list:
        if len(row) < 18:
            continue
        name = row[3]
        for keyword, index in attributes.items():
            if keyword in user_message and name.replace("さん", "") in user_message:
                value = row[index] if index < len(row) else "不明"
                found = True
                return f"{name}さんの{keyword}は {value} です。"
    if not found:
        logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return None
