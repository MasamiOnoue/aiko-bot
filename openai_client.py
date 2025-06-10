# openai_client.py
import os
import logging
from openai import OpenAI

# OpenAI APIキーの取得と検証
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logging.critical("❌ OPENAI_API_KEY が環境変数に設定されていません。")
    raise ValueError("OPENAI_API_KEY is not set.")

# OpenAI クライアントの初期化
try:
    client = OpenAI(api_key=api_key)
except Exception as e:
    logging.critical(f"❌ OpenAIクライアントの初期化に失敗しました: {e}")
    raise
