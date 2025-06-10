# company_info_load.py

import os
import json
import logging
from functools import lru_cache
import requests
from flask import jsonify, Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
import functions_framework

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')
GCF_ENDPOINT = os.getenv('GCF_ENDPOINT')  # Cloud FunctionsのURL
PRIVATE_API_KEY = os.getenv('PRIVATE_API_KEY')

# Cloud Functions本体（GCF上に配置する部分）
SHEET_MAP = {
    "会話ログ": SPREADSHEET_ID1,
    "従業員情報": SPREADSHEET_ID2,
    "取引先情報": SPREADSHEET_ID3,
    "会社情報": SPREADSHEET_ID4,
    "経験ログ": SPREADSHEET_ID5,
}

#Google Cloud Functionでファイルにアクセスできるようにする。
def get_google_sheets_service():
    credentials_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    
     # 修正ポイント：\\n → \n に戻す（この行が重要！）
    credentials_info["private_key"] = credentials_info["private_key"].replace("\\n", "\n")

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=credentials)
    return service

@functions_framework.http
def sheets_api_handler(request: Request):
    try:
        data = request.get_json()
        if not data or data.get("api_key") != PRIVATE_API_KEY:
            return jsonify({"status": "unauthorized"}), 403

        action = data.get("action")
        sheet_name = data.get("sheet_name")
        spreadsheet_id = SHEET_MAP.get(sheet_name)

        if not spreadsheet_id:
            return jsonify({"status": "error", "message": "Invalid sheet name"}), 400

        service = get_sheets_service()

        if action == "read":
            result = service.get(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A2:Z"
            ).execute()
            return jsonify({"status": "success", "rows": result.get("values", [])})

        elif action == "write":
            row = data.get("row")
            if not row or not isinstance(row, list):
                return jsonify({"status": "error", "message": "No row data provided"}), 400

            service.append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:Z",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]}
            ).execute()
            return jsonify({"status": "success", "mode": "write"})

        else:
            return jsonify({"status": "error", "message": "Unknown action"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Cloud Functionsを呼び出すクライアント側ラッパー

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
