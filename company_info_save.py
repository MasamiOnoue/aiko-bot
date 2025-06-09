#company_info_save.py

import os
import logging
from company_info_load import get_google_sheets_service

# === 会話ログ書き込み関数 ===
def write_conversation_log(sheet_values, timestamp, user_id, user_name, speaker, message, category):
    try:
        row = [timestamp, user_id, user_name, speaker, message, category, "text", "", "OK", ""]
        body = {"values": [row]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID1"),
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")

def write_employee_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID2"),
            range="従業員情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 従業員情報書き込みエラー: {e}")

def write_partner_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID3"),
            range="取引先情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 取引先情報書き込みエラー: {e}")

def write_company_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID4"),
            range="会社情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会社情報書き込みエラー: {e}")

def write_aiko_experience_log(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID5"),
            range="愛子の経験ログ!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 愛子の経験ログ書き込みエラー: {e}")


