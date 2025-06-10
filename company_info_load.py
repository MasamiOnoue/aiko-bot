# company_info_load.py

import os
import logging
from functools import lru_cache
import requests

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')
GCF_ENDPOINT = os.getenv('GCF_ENDPOINT')  # Cloud FunctionsのURL
PRIVATE_API_KEY = os.getenv('PRIVATE_API_KEY')

# Google Sheets APIのラッパー（Cloud Functions経由）
def call_cloud_function(action, sheet_name, payload=None):
    if not GCF_ENDPOINT or not PRIVATE_API_KEY:
        logging.error("❌ GCFの環境変数が設定されていません")
        return []

    try:
        request_payload = {
            "api_key": PRIVATE_API_KEY,
            "action": action,
            "sheet_name": sheet_name
        }
        if payload:
            request_payload.update(payload)

        response = requests.post(GCF_ENDPOINT, json=request_payload)
        if response.status_code == 200:
            return response.json().get("rows", [])
        else:
            logging.error(f"❌ Cloud Functionエラー: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
    return []

def get_conversation_log():
    return call_cloud_function("read", "会話ログ")

@lru_cache(maxsize=1)
def get_employee_info():
    return call_cloud_function("read", "従業員情報")

@lru_cache(maxsize=1)
def get_partner_info():
    return call_cloud_function("read", "取引先情報")

@lru_cache(maxsize=1)
def get_company_info():
    return call_cloud_function("read", "会社情報")

def get_experience_log():
    return call_cloud_function("read", "経験ログ")

def load_all_user_ids():
    employees = call_cloud_function("read", "従業員情報")
    return [row[11].strip() for row in employees if len(row) >= 12 and row[11].strip().startswith("U")]

def get_user_callname_from_uid(user_id):
    greetings_only = ["こんばんは", "こんばんわ", "こんにちわ", "こんにちは", "おはよう", "はろはろ","ハロー","おっはー","やっはろー","ばんわ","こんちわ"]
    if user_id.strip() in greetings_only:
        return ""

    employees = call_cloud_function("read", "従業員情報")
    for row in employees:
        if len(row) >= 12 and row[11].strip() == user_id:
            return row[3].replace("さん", "") if len(row) >= 4 else "不明"
    return "不明"
