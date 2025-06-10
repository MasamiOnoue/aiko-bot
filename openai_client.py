# openai_client.py
import os
from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ OPENAI_API_KEY が設定されていません。")

client = OpenAI(api_key=api_key)
