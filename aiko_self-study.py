# aiko_self_study.py

import requests
import hashlib
import time
import datetime
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Spreadsheet ID（会社情報）
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報

# 使用するスコープと認証情報
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
sheet_service = build("sheets", "v4", credentials=creds)

# ハッシュを記録する（前回の内容と比較するため）
HASH_FILE = "blog_hash.txt"

# ブログページの取得と解析
def fetch_blog_content():
    url = "https://sun-name.com/bloglist/"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        content_text = soup.get_text()
        return content_text.strip()
    except Exception as e:
        return f"[取得エラー]: {e}"

# ハッシュ化（変更検知）
def get_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

# スプレッドシートに内容を書き込む
def write_to_company_info(text):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    values = [[now, text]]
    request_body = {
        "values": values
    }
    try:
        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!D2",
            valueInputOption="USER_ENTERED",
            body=request_body
        ).execute()
        print(f"✅ 更新情報をD列に記録しました：{now}")
    except Exception as e:
        print(f"❌ スプレッドシート書き込み失敗: {e}")

# メイン処理
def check_blog_update():
    content = fetch_blog_content()
    new_hash = get_hash(content)

    old_hash = ""
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            old_hash = f.read().strip()

    if new_hash != old_hash:
        write_to_company_info(content)
        with open(HASH_FILE, "w") as f:
            f.write(new_hash)
    else:
        print("変化なし：更新はありませんでした。")

# 定期実行（6時間ごと）
if __name__ == "__main__":
    while True:
        print("🔍 ブログ更新チェックを実行中...")
        check_blog_update()
        time.sleep(6 * 60 * 60)  # 6時間待機
