# company_info.py（Google Sheets 連携＋会話ログ記録用）

import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

# Google Sheets API 接続サービスを返す関数
def get_google_sheets_service():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'aiko-bot-log-cfbf23e039fd.json')
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets()
    except Exception as e:
        logging.error(f"❌ Google Sheets認証エラー: {e}")
        return None

# 会話ログの保存関数（10列対応）
def append_conversation_log(spreadsheet_service, spreadsheet_id, timestamp, user_id, user_name, speaker, message, status):
    try:
        values = [[
            timestamp,
            user_id,
            user_name,
            speaker,
            message,
            "会話",           # カテゴリ
            "テキスト",       # メッセージタイプ
            "",              # 関連トピック（現状空）
            status,
            ""               # 感情ラベル（現状空）
        ]]
        spreadsheet_service.values().append(
            spreadsheetId=spreadsheet_id,
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            body={"values": values}
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログの追記に失敗: {e}")

# 各スプレッドシートIDの取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ
