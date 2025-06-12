import os
import requests
import logging

def send_conversation_log(timestamp, user_id, user_name, speaker, message, category, message_type, topic, status, sentiment=""):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-conversation-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {
            "timestamp": timestamp,
            "user_id": user_id,
            "user_name": user_name,
            "speaker": speaker,
            "message": message,
            "category": category,
            "message_type": message_type,
            "topic": topic,
            "status": status,
            "sentiment": sentiment
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 会話ログ送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def send_employee_info(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {
            "values": values
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 従業員情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def get_employee_info():
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "x-api-key": api_key
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ 従業員情報取得成功")
        return response.json().get("data", [])
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        return []
