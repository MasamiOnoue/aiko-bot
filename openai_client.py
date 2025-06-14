# openai_client.py
import os
import logging
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

def ask_openai_general_question(system_prompt, user_message, model="gpt-4o"):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ エラーが発生しました: {str(e)}"
