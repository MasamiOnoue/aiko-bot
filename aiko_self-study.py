# aiko_self_study.py

import requests
import hashlib
import time
import datetime
import os
import re
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import openai
import threading

# OpenAI APIキー（RenderのEnvironmentに登録されている）
openai.api_key = os.getenv("OPENAI_API_KEY")

# Spreadsheet ID（会社情報）
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報

# 使用するスコープと認証情報
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
sheet_service = build("sheets", "v4", credentials=creds)

# 会話ログ関連の読み込み
from company_info import get_conversation_log, load_all_user_ids

# キャッシュ（全体会話ログ50件、個別ログ20件）
user_conversation_cache = {}
full_conversation_cache = []

# 特定のワードを含む重要会話フラグ
IMPORTANT_PATTERNS = [
    "重要", "緊急", "至急", "要確認", "トラブル", "対応して", "すぐに", "大至急"
]

# 重要な会話を保存関数
def is_important_message(text):
    pattern = "|".join(map(re.escape, IMPORTANT_PATTERNS))
    return re.search(pattern, text, re.IGNORECASE) is not None

# 重要な会話を保存関数
def clean_log_message(text):
    patterns = [
        "覚えてください", "覚えて", "おぼえておいて", "覚えてね",
        "記録して", "メモして", "忘れないで", "記憶して",
        "保存して", "記録お願い", "記録をお願い"
    ]
    pattern = "|".join(map(re.escape, patterns))
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

# 重要な会話を保存関数
def cache_all_user_conversations():
    logs = get_conversation_log()
    all_user_ids = load_all_user_ids()

    global full_conversation_cache
    full_conversation_cache = []
    
    # 全体の最新50件をキャッシュ
    for log in logs[-100:]:
        if len(log) > 4:
            speaker = log[3]
            message = clean_log_message(log[4])
            flag = " [重要]" if is_important_message(message) else ""
            full_conversation_cache.append(f"{speaker}: {message}{flag}")

    # 各ユーザーの最新20件もキャッシュ
    for user_id in all_user_ids:
        user_logs = [
            f"{log[3]}: {clean_log_message(log[4])}{' [重要]' if is_important_message(log[4]) else ''}"
            for log in logs if len(log) > 4 and log[1] == user_id
        ][-20:]
        user_conversation_cache[user_id] = "\n".join(user_logs)

    print("🧠 会話キャッシュを更新しました")

# 10分ごとにキャッシュを更新
cache_thread = threading.Thread(target=lambda: periodic_cache_update(600), daemon=True)

# キャッシュ
def periodic_cache_update(interval):
    while True:
        cache_all_user_conversations()
        time.sleep(interval)

# 直近の会話の精査
def generate_contextual_reply(user_id, user_message):
    user_context = user_conversation_cache.get(user_id, "")
    others_context = "\n".join(full_conversation_cache)
    prompt = (
        f"以下はこのユーザーとの直近の会話と、社内で交わされた他の会話の記録です。文脈を踏まえて、自然に応答してください。\n"
        f"【このユーザーの履歴】\n{user_context}\n\n"
        f"【他の人の話題や社内背景】\n{others_context}\n\n"
        f"ユーザーの入力: {user_message}"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたはAIアシスタント愛子です。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[応答失敗]: {e}"

# 補足情報列の取得と書き込み
def get_existing_links():
    result = sheet_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID4,
        range="会社情報!F2"
    ).execute()
    values = result.get("values", [])
    return values[0][0] if values else ""

def update_links_and_log_diff(new_links_text, diff_summary):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    sheet_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID4,
        range="会社情報!F2",
        valueInputOption="USER_ENTERED",
        body={"values": [[new_links_text]]}
    ).execute()
    sheet_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID4,
        range="会社情報!G2",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[now, diff_summary]]}
    ).execute()

# サイト全体からリンクと中身を取得
def crawl_all_pages(base_url):
    try:
        response = requests.get(base_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        links = [a["href"] for a in soup.find_all("a", href=True) if base_url in a["href"]]
        unique_links = sorted(set(links))
        all_content = ""
        for link in unique_links:
            try:
                page = requests.get(link)
                page.raise_for_status()
                page_soup = BeautifulSoup(page.text, "html.parser")
                page_text = page_soup.get_text().strip()
                all_content += f"\n\n--- {link} ---\n{page_text}"
            except:
                continue
        return all_content
    except Exception as e:
        return f"[巡回エラー]: {e}"

# OpenAIで差分要約
def summarize_diff(old_text, new_text):
    prompt = (
        "以下はWebページの古い内容と新しい内容です。何が変更されたかを簡潔に日本語で要約してください。\n"
        "---古い内容---\n"
        f"{old_text[:3000]}\n"
        "---新しい内容---\n"
        f"{new_text[:3000]}"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは変更点を要約するアシスタントです。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[要約失敗]: {e}"

# メイン処理（毎日1回）
def check_full_site_update():
    print("🌐 サイト全体の巡回を開始します...")
    base_url = "https://sun-name.com/"
    new_content = crawl_all_pages(base_url)
    old_content = get_existing_links()

    if new_content.strip() != old_content.strip():
        diff_summary = summarize_diff(old_content, new_content)
        update_links_and_log_diff(new_content, diff_summary)
        print("✅ 差分あり：更新・記録しました")
    else:
        print("変化なし：更新はありませんでした。")

# 実行開始
if __name__ == "__main__":
    cache_thread.start()
    while True:
        now = datetime.datetime.now()
        if now.hour == 3:
            check_full_site_update()
            time.sleep(24 * 60 * 60)
        else:
            time.sleep(60 * 30)
