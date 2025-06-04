import os
import traceback
import logging
import datetime
import threading
import time
import requests
import json
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import set_user_agent
import googleapiclient.discovery

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')

# ✅ ここで creds を先に定義
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

# ✅ そのあとに AuthorizedSession を使う
import google.auth.transport.requests # タイムアウト付きHTTPオブジェクトの作成
from googleapiclient.http import HttpRequest

http = google.auth.transport.requests.AuthorizedSession(creds)  # 認証後に追加（タイムアウト付き HTTP クライアントを設定）
http.timeout = 90  # 秒数（必要に応じて延長）

# sheets_service を修正
sheets_service = build(
    'sheets',
    'v4',
    credentials=creds,
    cache_discovery=False,
)

sheet = sheets_service.spreadsheets()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 以下省略（元のコード続く）
