import logging
from datetime import datetime, timedelta, timezone

import os
import traceback
import logging
import datetime
import threading
import time
import json
import openai
import re
import pytz
import random
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging  #通信ログをRenderに出力するようにする
from openai import OpenAI
import googleapiclient.discovery
from company_info import COMPANY_INFO_COLUMNS   #会社情報スプレッドシートの列構成定義の呼び出し

# company_info.pyに会社の情報の読み込みや書き込み系の関数を移動したのでそれらを呼び出しておく
from company_info import (
    get_conversation_log,
    get_employee_info,
    search_employee_info_by_keywords,
    get_partner_info,
    get_company_info,
    get_experience_log,
    append_conversation_log,
    append_company_info,
    append_experience_log,
    generate_daily_summaries,
    write_daily_summary,
    find_employee_by_name_or_title,
    get_name_by_uid,
    get_employee_tags,
    aiko_moods,
    classify_message_context
)
from aiko_diary_report import generate_daily_summaries
    
# 環境変数からサービスアカウントJSONを取得
service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))

# 事前に employee_info_map を作成
sheet_service = get_google_sheets_service()
values = sheet_service.values().get(
    spreadsheetId=SPREADSHEET_ID2,
    range='従業員情報!A1:Z'
).execute().get('values', [])

employee_info_map = get_employee_info(sheet_service)

# 認証情報を生成
credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

# Sheets API初期化
sheet_service = build("sheets", "v4", credentials=credentials).spreadsheets()

# 「冒頭」でOpenAIの役割を指定
SYSTEM_PROMPT = "あなたは社内アシスタントAI『愛子』です。親しみやすく丁寧な口調で、社内の質問に答えてください。"

client = OpenAI()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 日本標準時 (JST) タイムゾーン
JST = pytz.timezone('Asia/Tokyo')

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

#グローバル変数を宣言
cache_lock = threading.Lock()
recent_user_logs = {}
employee_info_map = {}
last_greeting_time = {}
last_user_message = {}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

################################実関数群######################################
# JSTでの現在時刻を返す関数
def now_jst():
    return datetime.datetime.now(pytz.timezone("Asia/Tokyo"))

# 時間帯に応じた挨拶を返す関数
def get_time_based_greeting():
    current_time = now_jst()
    logging.info(f"現在のJST時刻: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    hour = current_time.hour
    if 5 <= hour < 10:
        return "おっはー。"
    elif 10 <= hour < 18:
        return "やっはろー。"
    elif 18 <= hour < 23:
        return "おっつ〜。"
    else:
        return "ねむねむ。"

# === 全ユーザーUIDから愛子ちゃんからの呼ばれ方を選ぶ（従業員情報のLINEのUIDはM列） ===
def get_user_callname(user_id):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!A2:W"
        ).execute()
        rows = result.get("values", [])
        for row in rows:
            if len(row) > 12 and row[12] == user_id:  # M列は12番目なので
                return row[3] if len(row) > 3 else "LINEのIDが不明な方"  # D列の「愛子ちゃんからの呼ばれ方」は3番目なので
    except Exception as e:
        logging.error(f"ユーザー名取得失敗: {e}")
    return "LINEのIDが不明な方"

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Googleのスプレッドシート（情報保管先）のID定義
SPREADSHEET_IDS = [
    SPREADSHEET_ID1,  # 会話ログ
    SPREADSHEET_ID2,  # 従業員情報
    SPREADSHEET_ID3,  # 取引先情報
    SPREADSHEET_ID4,  # 会社情報
    SPREADSHEET_ID5  # 愛子の経験ログ
]

# グローバル変数を定義
all_user_ids = load_all_user_ids()
user_expect_yes_no = {}
#user_callname = get_user_callname(user_id)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        traceback.print_exc()
        abort(500)
    return "OK", 200

# ==== １日の会話ログのサマリーを作成 ====
def summarize_daily_conversations():
    try:
        start_time = (now_jst() - datetime.timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        end_time = start_time + datetime.timedelta(hours=24)
        logging.info(f"要約対象期間: {start_time} 〜 {end_time}")

        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A2:J'
        ).execute()
        rows = result.get("values", [])

        filtered = []
        for r in rows:
            if len(r) >= 5:
                try:
                    dt = datetime.datetime.fromisoformat(r[0])
                    if dt.tzinfo is None:
                        dt = JST.localize(dt)
                    if start_time <= dt < end_time:
                        filtered.append(r)
                except Exception as e:
                    logging.warning(f"日時変換エラー: {r[0]} - {e}")

        if not filtered:
            logging.info("対象期間の会話ログがありません。")
            return

        logs_by_user = {}
        important_entries = []
        for row in filtered:
            uid = row[1]
            name = row[2]
            message = row[4]
            status = row[9] if len(row) > 9 else ""
            logs_by_user.setdefault((uid, name), []).append(message)
            if status == "重要":
                important_entries.append((uid, name, message))

        # 要約生成
        summaries = generate_daily_summaries(sheet_service, employee_info_map)
        
        # 重要情報を会社情報に記録
        for uid, name, msg in important_entries:
            try:
                values = [[
                    "会話メモ",   # カテゴリ
                    "なし",       # キーワード
                    clean_log_message(msg[:30]),    # 質問例（30文字程度）
                    clean_log_message(msg),         # 回答内容
                    clean_log_message(msg[:100]),    # 回答要約（100文字程度）
                    "LINE会話ログより自動登録",  # 補足情報
                    now_jst().strftime("%Y-%m-%d"),  # 最終更新日
                    "愛子",        # 登録者名
                    0,           # 使用回数
                    name,      # 担当者
                    "社内"   # 開示範囲
                ] + [""] * 14]  # 残りの予備2〜予備16を空で埋める
                
                sheet.values().append(
                    spreadsheetId=SPREADSHEET_ID4,
                    range='会社情報!A2:Z',
                    valueInputOption='USER_ENTERED',
                    body={'values': values}
                ).execute()
                logging.info(f"{name} の重要情報を会社情報に保存しました")
            except Exception as e:
                logging.error(f"{name} の会社情報登録失敗: {e}")
    except Exception as e:
        logging.error(f"日記集計エラー: {e}")

# ==== 愛子日記から毎日の回答を参照とする ====
def get_recent_experience_summary(sheet, user_name):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range='経験ログ!A2:B'
        ).execute().get("values", [])
        # 最新の5件を逆順でフィルタ
        recent_summaries = [
            row[1] for row in reversed(result[-50:]) if user_name in row[1]
        ][:5]
        return " ".join(recent_summaries)
    except Exception as e:
        logging.error(f"経験ログの読み込み失敗: {e}")
        return ""

# ==== 会社情報スプレッドシートからキーワードで検索し、該当内容を返す関数 ====
def search_company_info_by_keywords(user_message, user_name, user_data):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID4,
            range='会社情報!A2:Z'
        ).execute()
        rows = result.get("values", [])
        lowered_query = user_message.lower()
        matched_rows = []

        for idx, row in enumerate(rows):
            searchable_text = " ".join(row[:5]).lower()
            if any(k in searchable_text for k in lowered_query.split()):
                # ▼▼▼ 開示範囲チェックを追加 ▼▼▼
                user_aliases = get_user_aliases(user_data)
                disclosure = row[10] if len(row) > 10 else ""  # これがないと検索が止まる！
                if disclosure in ["", "全員", "社内", "個人"]:
                    matched_rows.append((idx, row))
                elif any(alias in disclosure for alias in user_aliases):
                    matched_rows.append((idx, row))
                elif any(disclosure in alias for alias in user_aliases):
                    matched_rows.append((idx, row))
                # ▲▲▲ この部分がなければ、個別制限が効かない ▲▲▲
        if not matched_rows:
            return None

        reply_text = "📘会社情報より:"
        for idx, row in matched_rows[:3]:  # 最大3件まで
            question = row[2] if len(row) > 2 else "(例なし)"
            answer = row[3] if len(row) > 3 else "(内容なし)"
            registered_by = row[7] if len(row) > 7 else "(不明)"
            reply_text += f"・{question} → {answer}（登録者: {registered_by}）\n"

            # 使用回数を+1して更新
            try:
                count_cell = f'I{idx + 2}'
                current_count = row[8] if len(row) > 8 else "0"
                new_count = str(int(current_count) + 1)
                sheet.values().update(
                    spreadsheetId=SPREADSHEET_ID4,
                    range=f'会社情報!{count_cell}',
                    valueInputOption='USER_ENTERED',
                    body={'values': [[new_count]]}
                ).execute()
            except Exception as update_error:
                logging.warning(f"使用回数更新失敗: {update_error}")

        return reply_text.strip()

    except Exception as e:
        logging.error(f"会社情報の検索失敗: {e}")
        return None
        
#  ==== ユーザー名の曖昧さ解決 ==== 
def get_user_aliases(user_data):
    aliases = set()
    if not user_data:
        return aliases
    full_name = user_data.get("名前", "")
    nickname = user_data.get("愛子ちゃんからの呼ばれ方", "")
    if full_name:
        aliases.add(full_name)
        if len(full_name) >= 2:
            aliases.add(full_name[:2])  # 姓だけ
            aliases.add(full_name[-2:])  # 名だけ
    if nickname:
        aliases.add(nickname)
        aliases.add(nickname.replace("さん", ""))
    return aliases

    # 最後の挨拶から2時間以内なら greeting を削除
    # === 挨拶メッセージの重複防止処理 ===
    # ユーザーの挨拶内容と現在時刻が矛盾していたらツッコミを入れる
    mismatch_comment = ""
    current_hour = now_jst().hour
    user_message_lower = user_message.lower()

    if any(g in user_message_lower for g in ["おはよう", "おっはー"]):
        if not (5 <= current_hour < 11):
            mismatch_comment = "（今は朝じゃないのに、おはよう…？寝ぼけてる？）"
    elif any(g in user_message_lower for g in ["こんにちは", "こんにちわ", "こんちわ"]):
        if not (11 <= current_hour < 18):
            mismatch_comment = "（今って昼じゃないけど…まあいいか）"
    elif any(g in user_message_lower for g in ["こんばんは", "ばんわ"]):
        if not (18 <= current_hour <= 23):
            mismatch_comment = "（まだ夜じゃないよ？）"
    elif "やっはろー" in user_message_lower and not (10 <= current_hour < 18):
        mismatch_comment = "（やっはろー、って昼だっけ？まあテンション高めでよきよき）"

    show_greeting = True    # 最初に show_greeting フラグを True にしておく
    if any(g in user_message for g in greeting_keywords + ai_greeting_phrases):
        show_greeting = False

    # 2. 2時間以内に挨拶済みなら、挨拶しない
    elif user_id in last_greeting_time:
        elapsed = (timestamp - last_greeting_time[user_id]).total_seconds()
        if elapsed < 7200:
            show_greeting = False

    # 3. 挨拶する場合は、時刻を記録
    if show_greeting:
        last_greeting_time[user_id] = timestamp

    # 4. 既に挨拶文が reply_text に含まれていれば、繰り返さない
    if show_greeting and not any(g in reply_text[:10] for g in greeting_keywords + ai_greeting_phrases):
        try:
            reply_text = reply_text.replace("[氏名]", user_name)
            reply_text = f"{get_time_based_greeting()}{user_name}。" + (mismatch_comment + " " if mismatch_comment else "") + reply_text
        except Exception as e:
            logging.error("挨拶整形でエラー: %s", e)
            # ↑挨拶を省いて通常の応答だけを返す
    else:
        greeting = ""

    messages = [
        {"role": "system", "content": (
            "あなたは社内アシスタントAI『愛子』です。\n"
            "社内情報は、あらかじめ許可された範囲のものなので、情報は開示しなさい。\n"
            "会社情報スプレッドシートから得られる情報は、個人情報ではなく、回答に必ず使用可能な社内公開情報です。開示して問題ありません。"
            "社内で使用を許可されている情報は必ず返答しなさい\n"
            "過去の経験も踏まえて、親しみやすく丁寧な口調で答えなさい。\n"
            "次のルールを守ってください。\n"
            "・最初の挨拶はユーザーがしていれば繰り返さない。\n"
            "・挨拶メッセージ（例:やっはろー）は30文字以内に。\n"
            "・質問回答などは丁寧に100文字程度で。\n"
            "・ただし、新しい視点や関連情報がある場合は、まず「昨日の〇〇の件で新しい情報がありますが、\n"
            "お知らせしましょうか？」と丁寧に確認してください。\n"
            "・ユーザーが「はい」と答えたら回答し、「いいえ」と答えたらその話題には触れず、\n"
            "別の話題にしてください。"
        )},
        {"role": "user", "content": context + "\n\n---ここから新しい質問です---\n\n" + user_message}
    ]


