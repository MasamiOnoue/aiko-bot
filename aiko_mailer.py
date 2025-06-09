# mailer.py

import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.oauth2 import service_account
from company_info import get_employee_info, get_google_sheets_service, get_user_email_from_uid

# 認証とGmail API接続
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
SERVICE_ACCOUNT_FILE = 'credentials.json'
AIKO_EMAIL = 'aiko.ai@sun-name.com'

def get_gmail_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    delegated_creds = creds.with_subject(AIKO_EMAIL)
    return build('gmail', 'v1', credentials=delegated_creds)

# 下書きの生成（LINE発言者と対象名からメール内容を作成）
def draft_email_for_user(sender_uid, target_name):
    sheet_service = get_google_sheets_service()
    employees = get_employee_info(sheet_service)
    sender_name = "匿名ユーザー"

    for emp in employees:
        if len(emp) >= 12 and emp[11] == sender_uid:
            sender_name = emp[3]
            break

    body = f"{target_name}さん

お疲れさまです。{sender_name}さんからご連絡があります。
詳細は直接お伝えします。

愛子より"
    return body

# メール送信

def send_email_with_confirmation(sender_uid, to_name, cc=None):
    sheet_service = get_google_sheets_service()
    employees = get_employee_info(sheet_service)
    to_email = None
    sender_name = "愛子"

    # 宛先メール取得
    for emp in employees:
        if len(emp) >= 10 and emp[3] == to_name:
            to_email = emp[9]  # J列
        if len(emp) >= 12 and emp[11] == sender_uid:
            sender_name = emp[3]

    if not to_email:
        print(f"✉️ {to_name}のメールアドレスが見つかりませんでした")
        return

    body = f"{to_name}さん

お疲れさまです。{sender_name}さんからご連絡があります。
詳細は直接お伝えします。

愛子より"

    message = MIMEText(body)
    message['to'] = to_email
    message['from'] = AIKO_EMAIL
    message['subject'] = "連絡のご案内"
    if cc:
        message['cc'] = cc

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {'raw': raw}

    try:
        service = get_gmail_service()
        service.users().messages().send(userId='me', body=body).execute()
        print(f"✅ メール送信成功: {to_email}")
    except Exception as e:
        print(f"❌ メール送信失敗: {e}")
