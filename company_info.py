# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

# Google Sheets 接続サービスの取得
def get_google_sheets_service():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'aiko-bot-log-cfbf23e039fd.json')
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets()
    except Exception as e:
        logging.error(f"❌ Google Sheets認証エラー: {e}")
        return None

################ 読み込み関数 ################

def get_conversation_log(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A2:J"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会話ログの取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_employee_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 従業員情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_partner_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID3,
            range="取引先情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 取引先情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_company_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会社情報の取得に失敗: {e}")
        return []

def get_experience_log(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range="経験ログ!A2:E"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 経験ログの取得に失敗: {e}")
        return []

################ 書き込み関数 ################

def write_conversation_log(sheet_service, timestamp, user_id, user_name, speaker, message, status):
    try:
        row = [timestamp, user_id, user_name, speaker, message, "", "text", "", status, ""]
        body = {"values": [row]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")

def write_aiko_experience_log(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID5,
            range="愛子の経験ログ!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 愛子の経験ログ書き込みエラー: {e}")

################ 補助関数 ################

def load_all_user_ids():
    try:
        service = get_google_sheets_service()
        result = service.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!M2:M"
        ).execute()
        values = result.get("values", [])
        return [row[0].strip() for row in values if row and row[0].strip().startswith("U") and len(row[0].strip()) >= 10]
    except Exception as e:
        logging.error(f"ユーザーIDリストの取得失敗: {e}")
        return []

def get_user_callname_from_uid(user_id):
    try:
        service = get_google_sheets_service()
        result = service.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:Z"
        ).execute()
        rows = result.get("values", [])
        for row in rows:
            if len(row) > 11 and row[11] == user_id:
                return row[3] if len(row) > 3 else "LINEのIDが不明な方"
    except Exception as e:
        logging.error(f"ユーザー名取得失敗: {e}")
    return "LINEのIDが不明な方"
