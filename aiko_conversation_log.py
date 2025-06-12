import requests
import datetime

def send_conversation_log():
    url = "https://write-read-commands-744246744291.asia-northeast1.run.app/write-conversation-log"
    headers = {"Content-Type": "application/json"}

    payload = {
        "timestamp": datetime.datetime.now().isoformat(),
        "user_id": "Uf1401051234b19ce0c53a10bb3f8433d",
        "user_name": "愛子",
        "speaker": "愛子",
        "message": "テストですわよ",
        "category": "テスト",
        "message_type": "テキスト",
        "topic": "テスト",
        "status": "OK",
        "sentiment": "テスト"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # HTTPエラーがあれば例外を発生
        print("✅ 書き込み成功:", response.json())
    except Exception as e:
        print("❌ 書き込みエラー:", type(e).__name__, e)
