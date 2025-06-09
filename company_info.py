# company_info.py（各種スプレッドシートの操作を担当）

import os
import logging
from functools import lru_cache
from google.oauth2 import service_account
from googleapiclient.discovery import build
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 環境変数からスプレッドシートIDを取得
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')

# Google Sheets 接続サービスの取得
def get_google_sheets_service():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'aiko-bot-log-cfbf23e039fd.json')
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets().values()
    except Exception as e:
        logging.error(f"❌ Google Sheets認証エラー: {e}")
        return None

# === 各種データ取得関数 ===

def get_conversation_log(sheet_values):
    try:
        result = sheet_values.get(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A2:J"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会話ログの取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_employee_info(sheet_values):
    try:
        result = sheet_values.get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 従業員情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_partner_info(sheet_values):
    try:
        result = sheet_values.get(
            spreadsheetId=SPREADSHEET_ID3,
            range="取引先情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 取引先情報の取得に失敗: {e}")
        return []

@lru_cache(maxsize=1)
def get_company_info(sheet_values):
    try:
        result = sheet_values.get(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 会社情報の取得に失敗: {e}")
        return []

def get_experience_log(sheet_values):
    try:
        result = sheet_values.get(
            spreadsheetId=SPREADSHEET_ID5,
            range="経験ログ!A2:E"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"❌ 経験ログの取得に失敗: {e}")
        return []

def load_all_user_ids():
    sheet = get_google_sheets_service().spreadsheets().values()
    result = sheet.get(
        spreadsheetId=SPREADSHEET_ID2,  # 従業員情報があるシートID
        range="従業員情報!L2:L"         # M列にUIDがある前提
    ).execute()
    values = result.get("values", [])
    return [row[0].strip() for row in values if row and row[0].strip().startswith("U")]

# === 書き込み関数 ===

def write_conversation_log(sheet_values, timestamp, user_id, user_name, speaker, message, status):
    try:
        row = [timestamp, user_id, user_name, speaker, message, "", "text", "", status, ""]
        body = {"values": [row]}
        sheet_values.append(
            spreadsheetId=SPREADSHEET_ID1,
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")

def write_employee_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 従業員情報書き込みエラー: {e}")

def write_partner_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=SPREADSHEET_ID3,
            range="取引先情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 取引先情報書き込みエラー: {e}")

def write_company_info(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=SPREADSHEET_ID4,
            range="会社情報!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会社情報書き込みエラー: {e}")

def write_aiko_experience_log(sheet_values, values):
    try:
        body = {"values": [values]}
        sheet_values.append(
            spreadsheetId=SPREADSHEET_ID5,
            range="愛子の経験ログ!A:E",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 愛子の経験ログ書き込みエラー: {e}")
        
def search_employee_info_by_keywords(user_message, employee_info_list):
    # 愛称辞書を定義
    alias_dict = {
        "おきく": "菊田京子",
        "まさみ": "政美",
        "たかし": "高橋",
        "ともこ": "友子",
        # 必要に応じて追加
    }
    attributes = {
        "役職": 4,
        "入社年": 5,
        "生年月日": 6,
        "性別": 7,
        "メールアドレス": 8,
        "個人メールアドレス": 9,
        "携帯電話番号": 10,
        "自宅電話": 11,
        "住所": 12,
        "郵便番号": 13,
        "緊急連絡先": 14,
        "ペット情報": 15,
        "性格": 16,
        "家族構成": 17
    }

    found = False
    user_message = user_message.replace("ちゃん", "さん").replace("君", "さん").replace("くん", "さん")
    # 愛称が含まれていれば正式名に置換
    for alias, real_name in alias_dict.items():
        if alias in user_message:
            user_message = user_message.replace(alias, real_name)  # ニックネーム対応

    for row in employee_info_list:
        if len(row) < 18:
            continue
        name = row[3]
        if not name:
            continue

        # フルネーム一致または「さん」付き名前一致
        if name in user_message or f"{name}さん" in user_message:
            for keyword, index in attributes.items():
                if keyword in user_message:
                    value = row[index] if index < len(row) and row[index].strip() != "" else "不明"
                    found = True
                    return f"{name}さんの{keyword}は {value} です。"

    if not found:
        logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return "申し訳ありませんが、該当の情報が見つかりませんでした。"

############## 補助系 ###########################

def classify_conversation_category(message):
    """
    OpenAIを使って会話内容をカテゴリ分類する。
    候補カテゴリ：「重要」「日常会話」「あいさつ」「業務情報」「その他」
    """
    prompt = (
        "以下の会話内容を、次のいずれかのカテゴリで1単語だけで分類してください："
        "「重要」「日常会話」「あいさつ」「業務情報」「その他」。\n\n"
        f"会話内容:\n{message}\n\n"
        "カテゴリ名だけを返してください。"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは優秀な会話分類AIです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,
            temperature=0
        )
        category = response.choices[0].message.content.strip()
        return category
    except Exception as e:
        logging.error(f"❌ カテゴリ分類失敗: {e}")
        return "未分類"

def get_user_callname_from_uid(user_id):
    """
    従業員情報から UID に対応する呼び名（D列）を取得する。
    """
    sheet = get_google_sheets_service()
    try:
        result = sheet.get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!D2:L"
        ).execute()
        values = result.get("values", [])
        for row in values:
            if len(row) >= 9 and row[8].strip() == user_id:
                return row[0].strip() if row[0].strip() else "不明"
    except Exception as e:
        logging.error(f"❌ 呼び名取得失敗: {e}")
    return "不明"
