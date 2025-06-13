from aiko_greeting import now_jst
from write_conversation_log import write_conversation_log  # Flask内で定義した関数

def log_aiko_reply(user_id, user_name, message, speaker, category, message_type, topic, status, sentiment="", sheet_service=None):
    try:
        timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")
        write_conversation_log(
            sheet_service,
            timestamp=timestamp,
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
    except Exception as e:
        logging.exception(f"❌ log_aiko_reply エラー: {e}")
