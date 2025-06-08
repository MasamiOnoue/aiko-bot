# aiko_self_study.py

import requests
import hashlib
import time
import datetime
import os
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import openai

# OpenAI APIキー（RenderのEnvironmentに登録されている）
openai.api_key = os.getenv("OPENAI_API_KEY")

# Spreadsheet ID（会社情報）
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報

# 使用するスコープと認証情報
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
sheet_service = build("sheets", "v4", credentials=creds)

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
    # 補足情報（F列）更新
    sheet_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID4,
        range="会社情報!F2",
        valueInputOption="USER_ENTERED",
        body={"values": [[new_links_text]]}
    ).execute()
    # 差分履歴（G列以降）に追記
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

# 毎日午前3時に実行（実運用ではcron推奨）
if __name__ == "__main__":
    while True:
        now = datetime.datetime.now()
        if now.hour == 3:
            check_full_site_update()
            time.sleep(24 * 60 * 60)  # 24時間待機
        else:
            time.sleep(60 * 30)  # 30分ごとに再確認
