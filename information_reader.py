import os
import json
import logging
import datetime
import pytz
import re
import requests

from sheets_service import get_google_sheets_service

# Google Sheets IDの環境変数
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID4")
SHEET_NAME = "会話ログ"

# Sheets APIクライアント
sheets_service = get_google_sheets_service()

# キャッシュ（セッション内保持用）
user_conversation_cache = {}
full_conversation_cache = []

# 重要ワードパターン
IMPORTANT_PATTERNS = [
    "重要", "緊急", "至急", "要確認", "トラブル", "対応して", "すぐに", "大至急"
]

def is_important_message(text):
    pattern = "|".join(map(re.escape, IMPORTANT_PATTERNS))
    return re.search(pattern, text, re.IGNORECASE) is not None

def clean_log_message(text):
    patterns = [
        "覚えてください", "覚えて", "記録して", "メモして", "お願い"
    ]
    for p in patterns:
        text = text.replace(p, "")
    return text.strip()

def read_conversation_log():
    """
    Cloud Run 経由で会話ログを取得し、キャッシュとして保持する。
    初回読み込み時のみAPIを叩く。
    """
    global full_conversation_cache
    if full_conversation_cache:
        return full_conversation_cache

    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-conversation-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        records = result.get("records", [])

        full_conversation_cache = records
        return records

    except Exception as e:
        logging.error(f"❗Cloud Run経由の会話ログ取得に失敗しました: {e}")
        return []

def get_user_conversation(user_id: str, limit: int = 20):
    """
    指定されたユーザーIDの会話履歴を取得する（最大limit件まで）。
    キャッシュがあればそれを優先的に使用し、なければ全体ログから取得する。
    """
    if user_id in user_conversation_cache:
        return user_conversation_cache[user_id][-limit:]

    all_logs = read_conversation_log()
    filtered_logs = [log for log in all_logs if log.get("user_id") == user_id]
    sorted_logs = sorted(filtered_logs, key=lambda x: x.get("タイムスタンプ", ""), reverse=True)
    result = sorted_logs[:limit][::-1]  # 時系列順で返す
    user_conversation_cache[user_id] = sorted_logs
    return result

def get_latest_conversation_by_user():
    all_logs = read_conversation_log()
    latest_logs = {}
    for log in reversed(all_logs):
        uid = log.get("user_id")
        if uid and uid not in latest_logs:
            latest_logs[uid] = log
    return latest_logs

def search_conversation_log(query, conversation_logs):
    """
    会話ログの中からクエリにマッチするメッセージを検索する。
    """
    results = []
    for log in conversation_logs:
        if query in log.get("メッセージ", ""):
            results.append(log)
    return results

def read_employee_info():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 従業員情報取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_company_info():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-company-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 会社情報取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_partner_info():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-partner-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 取引先情報取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_aiko_experience_log():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-aiko-experience-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 経験ログ取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_task_info():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-task-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ タスク情報取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_attendance_log():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-attendance-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 勤怠ログ取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []

def read_recent_conversation_log(user_id, limit=20):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        url = base_url.rstrip("/") + "/read-conversation-log"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": os.getenv("PRIVATE_API_KEY", "")
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json().get("records", [])
        user_messages = [
            {
                "role": "user" if row["speaker"] == row["user_name"] else "assistant",
                "content": row["message"]
            }
            for row in reversed(data)
            if row.get("user_id") == user_id
        ]
        return user_messages[:limit]
    except Exception as e:
        logging.error(f"❌ 会話履歴取得エラー: {e}")
        return []
