# company_info_save.py

import os
import logging
import requests
from company_info_load import get_google_sheets_service

# === 会話ログ書き込み関数 ===
def write_conversation_log(sheet_service, timestamp, user_id, user_name, speaker, message, category, message_type, topics, status):
    try:
        if "GCF_ENDPOINT" not in os.environ or "PRIVATE_API_KEY" not in os.environ:
            logging.error("❌ GCFの環境変数が設定されていません")
            return

        payload = {
            "sheet": "会話ログ",
            "values": [[timestamp, user_id, user_name, speaker, message, category, message_type, topics, status]]
        }
        headers = {"x-api-key": os.environ["PRIVATE_API_KEY"]}
        response = requests.post(os.environ["GCF_ENDPOINT"], json=payload, headers=headers)

        if response.status_code != 200:
            logging.error(f"❌ GCF書き込み失敗: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")

def write_employee_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID2"),
            range="従業員情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 従業員情報書き込みエラー: {e}")

def write_partner_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID3"),
            range="取引先情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 取引先情報書き込みエラー: {e}")

def write_company_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID4"),
            range="会社情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会社情報書き込みエラー: {e}")

def write_aiko_experience_log(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID5"),
            range="愛子の経験ログ!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 愛子の経験ログ書き込みエラー: {e}")
