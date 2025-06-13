# aiko_helpers.py

from information_writer import write_conversation_log  # ✅ 新しい書き込み先
from aiko_greeting import now_jst

# ✅ 新しく直接Cloud Functions経由で書き込み
GCF_ENDPOINT = os.getenv("GCF_WRITE_CONVERSATION_LOG_URL")
PRIVATE_API_KEY = os.getenv("PRIVATE_API_KEY")

def log_aiko_reply(user_id, user_name, message, speaker, category, message_type, topic, status, sentiment=""):
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")
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
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {PRIVATE_API_KEY}"
        }
        response = requests.post(GCF_ENDPOINT, json=payload, headers=headers, timeout=5)

        if response.status_code == 200:
            logging.info("✅ 会話ログ送信成功")
        else:
            logging.error(f"❌ 書き込み失敗: {response.text}")
    except requests.exceptions.Timeout:
        logging.error("❌ 書き込みタイムアウト")
    except Exception as e:
        logging.exception(f"❌ log_aiko_reply 例外: {e}")
