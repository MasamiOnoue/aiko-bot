# aiko_self_study.py

import os
import time
import re
import datetime
import requests
import threading
from typing import List, Dict
from bs4 import BeautifulSoup
from sheets_service import get_google_sheets_service
from openai import OpenAI
from openai_client import client

SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
sheets_service = get_google_sheets_service()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

user_conversation_cache = {}
full_conversation_cache = []

IMPORTANT_PATTERNS = [
    "重要", "緊急", "至急", "要確認", "トラブル", "対応して", "すぐに", "大至急"
]

def is_important_message(text):
    pattern = "|".join(map(re.escape, IMPORTANT_PATTERNS))
    return re.search(pattern, text, re.IGNORECASE) is not None

def clean_log_message(text):
    patterns = [
        "覚えてください", "覚えて", "おぼえておいて", "覚えてね",
        "記録して", "メモして", "忘れないで", "記憶して",
        "保存して", "記録お願い", "記録をお願い"
    ]
    pattern = "|".join(map(re.escape, patterns))
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

def build_conversational_prompt(conversation_history: List[Dict], latest_user_message: str) -> List[Dict]:
    """
    GPT用の会話プロンプトを構築する。
    """
    messages = []
    system_prompt = {
        "role": "system",
        "content": (
            "あなたは、株式会社サンネームの社内で利用されているLINEアシスタント『愛子』です。"
            "愛子は2005年9月21日生まれのデジタル秘書で、まじめで丁寧、自然なトーンで話します。"
            "敬語を使いつつも、親しみやすさを忘れず、短く簡潔な表現を心がけています。"
            "質問には可能な限り正確かつ即答し、必要であれば過去の会話も踏まえて自然な応答をしてください。"
            "情報が不足している場合は、必要な情報を簡潔に尋ねてください。"
        )
    }
    messages.append(system_prompt)
    for entry in conversation_history[-20:]:
        role = "user" if entry["speaker"] == "user" else "assistant"
        messages.append({"role": role, "content": entry["message"]})
    messages.append({"role": "user", "content": latest_user_message})
    return messages

def generate_contextual_reply_from_context(system_prompt, context, user_message):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context + "\n\n" + user_message}
    ]
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # または gpt-3.5-turbo
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ エラーが発生しました: {str(e)}"
