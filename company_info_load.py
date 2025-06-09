# company_info_load.py

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

def get_conversation_log(sheet_values):
    try:
        result = sheet_values.get(spreadsheetId=SPREADSHEET_ID1, range="会話ログ!A2:J").execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会話ログの取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_employee_info(sheet_values):
    try:
        result = sheet_values.get(spreadsheetId=SPREADSHEET_ID2, range="従業員情報!A2:Z").execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 従業員情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_partner_info(sheet_values):
    try:
        result = sheet_values.get(spreadsheetId=SPREADSHEET_ID3, range="取引先情報!A2:Z").execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 取引先情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_company_info(sheet_values):
    try:
        result = sheet_values.get(spreadsheetId=SPREADSHEET_ID4, range="会社情報!A2:Z").execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会社情報の取得に失敗: {e}")
        return []

def get_experience_log(sheet_values):
    try:
        result = sheet_values.get(spreadsheetId=SPREADSHEET_ID5, range="経験ログ!A2:E").execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 経験ログの取得に失敗: {e}")
        return []

def load_all_user_ids():
    sheet = get_google_sheets_service()
    if not sheet:
        logging.error("❌ シートサービスの取得に失敗しました")
        return []
    result = sheet.get(spreadsheetId=SPREADSHEET_ID2, range="従業員情報!L2:L").execute()
    values = result.get("values", [])
    return [row[0].strip() for row in values if row and row[0].strip().startswith("U")]

def get_user_callname_from_uid(user_id):
    sheet = get_google_sheets_service()
    if not sheet:
        logging.error("❌ Google Sheetsサービス取得に失敗しました")
        return "不明"
    try:
        result = sheet.get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!D2:L"
        ).execute()
        values = result.get("values", [])

        greetings_only = ["こんばんは", "こんばんわ", "こんにちわ", "こんにちは", "おはよう"]
        if user_id.strip() in greetings_only:
            return ""

        for row in values:
            if len(row) >= 9 and row[8].strip() == user_id:
                name = row[0].strip() if row[0].strip() else "不明"
                return name.replace("さん", "")
    except Exception as e:
        logging.error(f"❌ UIDの読み込みに失敗しました: {e}")
    return "不明"
