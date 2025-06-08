# company_info.py

import os
import logging
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Google Sheets APIの認証を行う関数
def get_google_sheets_service():
    try:
        service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets()
    except Exception as e:
        logging.error(f"❌ Google Sheets APIの認証に失敗: {e}")
        return None

# スプレッドシートIDを環境変数から取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

# データ取得の共通関数
def get_sheet_values(sheet_service, spreadsheet_id, range_name):
    try:
        result = sheet_service.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get('values', [])
    except Exception as e:
        logging.error(f"❌ シートの読み込みに失敗しました: {e}")
        return []

# それぞれのデータ取得関数（必要に応じて拡張可）
def get_conversation_log(sheet_service):
    return get_sheet_values(sheet_service, SPREADSHEET_ID1, "会話ログ!A2:Z")

def get_employee_info(sheet_service):
    return get_sheet_values(sheet_service, SPREADSHEET_ID2, "従業員情報!A2:Z")

def get_partner_info(sheet_service):
    return get_sheet_values(sheet_service, SPREADSHEET_ID3, "取引先情報!A2:Z")

def get_company_info(sheet_service):
    return get_sheet_values(sheet_service, SPREADSHEET_ID4, "会社情報!A2:Z")

def get_aiko_experience_log(sheet_service):
    return get_sheet_values(sheet_service, SPREADSHEET_ID5, "愛子経験ログ!A2:Z")
