# aiko_self_study.py　愛子が自分で勉強をする関数群

import requests
import hashlib
import time
import datetime
import os
import re
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from openai import OpenAI
import threading
from company_info_load import get_user_callname_from_uid, load_all_user_ids, get_conversation_log, get_google_sheets_service
from company_info_save import write_company_info

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
sheet_service = get_google_sheets_service()

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

def store_important_message_to_company_info(message, user_id):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    callname = get_user_callname_from_uid(user_id) or "不明"
    row_data = [["", message, "", "愛子", "", "", "", now, 1, callname, "全員"]]
    sheet_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID4,
        range="会社情報!A2",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": row_data}
    ).execute()

def cache_all_user_conversations():
    logs = get_conversation_log()
    all_user_ids = load_all_user_ids()

    global full_conversation_cache
    full_conversation_cache = []

    for log in logs[-100:]:
        if len(log) > 4:
            speaker = log[3]
            message = clean_log_message(log[4])
            flag = " [重要]" if is_important_message(message) else ""
            full_conversation_cache.append(f"{speaker}: {message}{flag}")
            if is_important_message(message):
                store_important_message_to_company_info(message, log[1])

    for user_id in all_user_ids:
        user_logs = [
            f"{log[3]}: {clean_log_message(log[4])}{' [重要]' if is_important_message(log[4]) else ''}"
            for log in logs if len(log) > 4 and log[1] == user_id
        ][-20:]
        user_conversation_cache[user_id] = "\n".join(user_logs)

    print("🧠 会話キャッシュを更新しました")

def periodic_cache_update(interval):
    while True:
        cache_all_user_conversations()
        time.sleep(interval)

cache_thread = threading.Thread(target=lambda: periodic_cache_update(600), daemon=True)

def generate_contextual_reply(user_id, user_message):
    user_context = user_conversation_cache.get(user_id, "")
    others_context = "\n".join(full_conversation_cache)
    prompt = (
        "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示しなさい。\n"
        "以下はこのユーザーとの直近の会話と、社内で交わされた他の会話の記録です。文脈を踏まえて、自然に応答してください。\n"
        f"【このユーザーの履歴】\n{user_context}\n\n"
        f"【他の人の話題や社内背景】\n{others_context}\n\n"
        f"ユーザーの入力: {user_message}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたはAIアシスタント愛子です。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[応答失敗]: {e}"

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

def summarize_diff(old_text, new_text):
    prompt = (
        "以下はWebページの古い内容と新しい内容です。何が変更されたかを簡潔に日本語で要約してください。\n"
        "---古い内容---\n"
        f"{old_text[:3000]}\n"
        "---新しい内容---\n"
        f"{new_text[:3000]}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは変更点を要約するアシスタントです。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[要約失敗]: {e}"

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

if __name__ == "__main__":
    cache_thread.start()
    while True:
        now = datetime.datetime.now()
        if now.hour == 3:
            check_full_site_update()
            time.sleep(24 * 60 * 60)
        else:
            time.sleep(60 * 30)
