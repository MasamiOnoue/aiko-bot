# aiko_helpers.py

from aiko_conversation_log import send_conversation_log
from aiko_greeting import now_jst

def log_aiko_reply(user_id, user_name, message, category="通常応答", topic="AI応答", status="OK", message_type="テキスト", speaker="愛子", sentiment=""):
    logging.info(f"🔁 愛子からの返信メッセージ: {speaker} - {message}")
    send_conversation_log(
        timestamp=now_jst().strftime("%Y-%m-%d %H:%M:%S"),
        user_id=user_id,
        user_name=user_name,
        speaker=speaker,
        message=message,
        category=category,
        message_type=message_type,
        topic=topic,
        status=status,
        sentiment=sentiment
    )
