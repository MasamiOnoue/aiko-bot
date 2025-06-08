# aiko_emergency_procedure.py
# 異常系の処理などを専用で集めたPythonスクリプト

import logging
from linebot.models import TextSendMessage

def handle_emergency_reply(line_bot_api, reply_token, error: Exception = None):
    """
    愛子が応答できないときに代替メッセージを送る
    """
    if error:
        logging.error(f"❗ 応答失敗: {error}")
    try:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="すみません、現在応答が遅れているようです。もう一度お試しください。")
        )
    except Exception as ee:
        logging.critical(f"‼️ 緊急返信すら失敗: {ee}")
