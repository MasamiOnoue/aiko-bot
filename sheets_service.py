import os
import json
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ✅ Google Sheets API サービスを取得

def get_google_sheets_service():
    try:
        credentials_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        credentials_info["private_key"] = credentials_info["private_key"].replace("\\n", "\n")

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=credentials)
    except Exception as e:
        logging.error(f"❌ Google Sheetsサービス初期化エラー: {e}")
        return None
