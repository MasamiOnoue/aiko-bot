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

################ 各種読み込み関数 ###############
# 会話ログをスプレッドシートから取得（全行）
def get_conversation_log(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A2:J"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会話ログの取得に失敗: {e}")
        return []

# 従業員情報を取得する関数（UIDをキーに、A〜Z列まで対応）
def get_employee_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:Z"
        ).execute()
        rows = result.get("values", [])
        employee_info_map = {}
        for row in rows:
            if len(row) >= 12:
                user_uid = row[11]
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
                    "備考2": row[23] if len(row) > 23 else "",
                    "備考3": row[24] if len(row) > 24 else "",
                    "備考4": row[25] if len(row) > 25 else "",
                }
        return employee_info_map
    except Exception as e:
        logging.error(f"❌ 従業員情報の取得に失敗: {e}")
        return {}

# 取引先情報を取得する関数（A〜Z列対応）
def get_partner_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID3,
            range="取引先情報!A2:Z"
        ).execute()
        rows = result.get("values", [])
        partner_info_list = []
        for row in rows:
            partner_info = {
                "顧客ID": row[0] if len(row) > 0 else "",
                "会社名": row[1] if len(row) > 1 else "",
                "読み": row[2] if len(row) > 2 else "",
                "部署名": row[3] if len(row) > 3 else "",
                "担当者名": row[4] if len(row) > 4 else "",
                "電話番号": row[5] if len(row) > 5 else "",
                "FAX": row[6] if len(row) > 6 else "",
                "メール": row[7] if len(row) > 7 else "",
                "郵便番号": row[8] if len(row) > 8 else "",
                "住所": row[9] if len(row) > 9 else "",
                "取引開始日": row[10] if len(row) > 10 else "",
                "最終連絡日": row[11] if len(row) > 11 else "",
                "契約ステータス": row[12] if len(row) > 12 else "",
                "見積履歴リンク": row[13] if len(row) > 13 else "",
                "対応履歴リンク": row[14] if len(row) > 14 else "",
                "備考欄": row[15] if len(row) > 15 else "",
                "サブ担当1": row[16] if len(row) > 16 else "",
                "サブ担当2": row[17] if len(row) > 17 else "",
                "サブ担当4": row[18] if len(row) > 18 else "",
                "歴史": row[19] if len(row) > 19 else "",
                "略称1": row[20] if len(row) > 20 else "",
                "略称2": row[21] if len(row) > 21 else "",
                "略称3": row[22] if len(row) > 22 else "",
                "予備1": row[23] if len(row) > 23 else "",
                "予備2": row[24] if len(row) > 24 else "",
                "予備3": row[25] if len(row) > 25 else "",
            }
            partner_info_list.append(partner_info)
        return partner_info_list
    except Exception as e:
        logging.error(f"❌ 取引先情報の取得に失敗: {e}")
        return []

# 会社情報を取得する関数（A〜Z列対応）
def get_company_info(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!A2:Z"
        ).execute()
        rows = result.get("values", [])
        headers = [
            "カテゴリ",
            "キーワード",
            "質問例",
            "回答内容",
            "回答要約",
            "補足情報",
            "最終更新日",
            "登録者名",
            "使用回数",
            "担当者",
            "開示範囲",
            "予備2",
            "予備3",
            "予備4",
            "予備5",
            "予備6",
            "予備7",
            "予備8",
            "予備9",
            "予備10",
            "予備11",
            "予備12",
            "予備13",
            "予備14",
            "予備15",
            "予備16"
        ]
        structured_data = []
        for row in rows:
            entry = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            structured_data.append(entry)
        return structured_data
    except Exception as e:
        logging.error(f"❌ 会社情報の取得に失敗: {e}")
        return []

# 愛子の経験ログを取得する関数（A列:日付、B列:日記）
def get_experience_log(sheet_service):
    try:
        result = sheet_service.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range="経験ログ!A2:E"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 経験ログの取得に失敗: {e}")
        return []

################ 書き込み関数：統一 ###############
#会話ログを書き込む
def write_conversation_log(sheet_service, timestamp, user_id, user_name, speaker, message, status):
    try:
        row = [
            timestamp,
            user_id,
            user_name,
            speaker,
            message,
            "",  # カテゴリ
            "text",  # メッセージタイプ
            "",  # 関連トピック
            status,
            ""   # 感情ラベル
        ]
        body = {"values": [row]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")
        
#従業員情報を書き込む
def write_employee_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 従業員情報書き込みエラー: {e}")

#取引先情報を書き込む
def write_partner_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID3,
            range="取引先情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 取引先情報書き込みエラー: {e}")
        
#会社情報（ノウハウ）を書き込む
def write_company_info(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会社情報書き込みエラー: {e}")
        
#愛子の日記（経験ログ）を書き込む
def write_aiko_experience_log(sheet_service, values):
    try:
        body = {"values": [values]}
        sheet_service.values().append(
            spreadsheetId=SPREADSHEET_ID5,
            range="愛子の経験ログ!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 愛子の経験ログ書き込みエラー: {e}")

