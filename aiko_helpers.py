import os
import requests
import logging
from aiko_greeting import now_jst

def log_aiko_reply(timestamp, user_id, user_name, speaker, reply, category, message_type, topics, status, topic, sentiment):
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")  # 再上書きしても問題なし
        GCF_ENDPOINT = os.getenv("GCF_ENDPOINT")
        API_KEY = os.getenv("PRIVATE_API_KEY")

        if not GCF_ENDPOINT or not API_KEY:
            logging.error("❌ GCF_ENDPOINTまたはAPI_KEYが未設定")
            return

        url = f"{GCF_ENDPOINT.rstrip('/')}/write-conversation-log"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY
        }

        payload = {
            "timestamp": timestamp,
            "user_id": user_id,
            "user_name": user_name,
            "speaker": speaker,
            "message": reply,  # ← ここを修正！
            "category": category,
            "message_type": message_type,
            "topic": topic,
            "status": status,
            "sentiment": sentiment
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            logging.info("✅ 会話ログ送信成功")
        else:
            logging.error(f"❌ 書き込み失敗: {response.status_code} - {response.text}")

    except Exception as e:
        logging.exception(f"❌ log_aiko_reply 例外: {e}")
