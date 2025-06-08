# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

# Google Sheets 接続サービスの取得
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

# 会話ログをスプレッドシートに記録（10列）
def append_conversation_log(sheet_service, spreadsheet_id, timestamp, user_id, user_name, speaker, message, status):
    try:
        row = [
            timestamp,
            user_id,
            user_name,
            speaker,
            message,
            "",  # F列: カテゴリ
            "text",  # G列: メッセージタイプ（暫定）
            "",  # H列: 関連トピック
            status,
            ""   # J列: 感情ラベル
        ]
        body = {"values": [row]}
        sheet_service.values().append(
            spreadsheetId=spreadsheet_id,
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログの追記に失敗: {e}")

# 従業員情報を取得する関数（UIDをキーに、A〜W列まで対応）
def get_employee_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:W"
        ).execute()
        rows = result.get("values", [])
        employee_info_map = {}
        for row in rows:
            if len(row) >= 12:  # UIDが存在するか確認（L列）
                user_uid = row[11]  # LINEのUID（L列）
                employee_info_map[user_uid] = {
                    "名前": row[0] if len(row) > 0 else "",
                    "名前の読み": row[1] if len(row) > 1 else "",
                    "呼ばれ方": row[2] if len(row) > 2 else "",
                    "愛子ちゃんからの呼ばれ方": row[3] if len(row) > 3 else "",
                    "愛子からの呼ばれ方２（よみ）": row[4] if len(row) > 4 else "",
                    "役職": row[5] if len(row) > 5 else "",
                    "入社年": row[6] if len(row) > 6 else "",
                    "生年月日": row[7] if len(row) > 7 else "",
                    "性別": row[8] if len(row) > 8 else "",
                    "メールアドレス": row[9] if len(row) > 9 else "",
                    "LINE ID": row[10] if len(row) > 10 else "",
                    "LINEのUID": row[11],
                    "古いメールアドレス": row[12] if len(row) > 12 else "",
                    "個人メールアドレス": row[13] if len(row) > 13 else "",
                    "携帯電話番号": row[14] if len(row) > 14 else "",
                    "自宅電話": row[15] if len(row) > 15 else "",
                    "住所": row[16] if len(row) > 16 else "",
                    "郵便番号": row[17] if len(row) > 17 else "",
                    "緊急連絡先": row[18] if len(row) > 18 else "",
                    "ペット情報": row[19] if len(row) > 19 else "",
                    "性格": row[20] if len(row) > 20 else "",
                    "家族構成": row[21] if len(row) > 21 else "",
                    "備考1": row[22] if len(row) > 22 else "",
                }
        return employee_info_map
    except Exception as e:
        logging.error(f"❌ 従業員情報の取得に失敗: {e}")
        return {}
