# information_writer.py

import os
import requests
import logging

def write_conversation_log(timestamp, user_id, user_name, speaker, message, category, message_type, topic, status, sentiment="", reserve1="", reserve2="", reserve3=""):
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
        # JSTで送信されているか確認、UTCとの二重登録を防ぐ
        if "+" not in timestamp:
            from datetime import datetime
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            try:
                # UTCで誤っていたらJSTに変換
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                dt = pytz.utc.localize(dt).astimezone(jst)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logging.warning(f"⚠️ タイムスタンプ変換失敗: {e}")

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
            "sentiment": sentiment,
            "reserve1": reserve1,
            "reserve2": reserve2,
            "reserve3": reserve3
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 会話ログ送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
        
def write_employee_info(values):
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
        payload = {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 従業員情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def write_company_info(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-company-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 会社情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def write_partner_info(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-partner-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 取引先情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def write_aiko_experience_log(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-aiko-experience-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 経験ログ送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def write_task_info(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-task-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = values if isinstance(values, dict) else {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ タスク情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")

def write_attendance_log(values):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/write-attendance-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {"values": values}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ 勤怠情報送信成功")
    except Exception as e:
        logging.error(f"❌ Cloud Function呼び出し失敗: {e}")
