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

#googleのDriveファイルにアクセスする関数の定義
def get_google_sheets_service():
    service_account_info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=credentials).spreadsheets()
    
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

def now_jst():
    return datetime.datetime.now(pytz.timezone("Asia/Tokyo"))

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

def get_user_summary(user_id):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range='経験ログ!A2:D'
        ).execute()
        rows = result.get("values", [])
        for row in reversed(rows):
            if row[1] == user_id and len(row) >= 4:
                return row[3]  # 要約内容
    except Exception as e:
        logging.error(f"{user_id} の経験ログ取得失敗: {e}")
    return ""
    
# キャッシュをリフレッシュする
def refresh_cache():
    global recent_user_logs
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A2:J'
        ).execute()
        rows = result.get("values", [])[-100:]
        with cache_lock:
            recent_user_logs = {
                row[1]: [r for r in rows if r[1] == row[1] and r[3] == "ユーザー"][-10:]
                for row in rows if len(row) >= 4
            }
    except Exception as e:
        logging.error("キャッシュ更新失敗: %s", e)

def load_employee_info():
    global employee_info_map
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range='従業員情報!A1:Z'  # ← A1:Z に要修正
        ).execute()
        rows = result.get("values", [])
        headers = rows[0]
        for row in rows[1:]:
            data = dict(zip(headers, row))
            uid = data.get("LINEのUID")
            if uid:
                employee_info_map[uid] = data
    except Exception as e:
        logging.error("従業員情報の読み込み失敗: %s", e)

threading.Thread(target=lambda: (lambda: [refresh_cache() or load_employee_info() or time.sleep(300) for _ in iter(int, 1)])(), daemon=True).start()

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

# === 全ユーザーのUIDの読み込み（従業員情報のM列にあるLINEのUID） ===
def load_all_user_ids():
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range="従業員情報!M2:M"
        ).execute()
        values = result.get("values", [])
        # UIDの形式として：Uで始まり長さが10文字以上のものだけを採用
        return [
            row[0].strip()
            for row in values
            if row and row[0].strip().startswith("U") and len(row[0].strip()) >= 10
        ]
    except Exception as e:
        logging.error(f"ユーザーIDリストの取得失敗: {e}")
        return []
        
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

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="愛子です。お友だち登録ありがとうございます。")
    )

# ==== キーワードから取引先情報から情報を取ってくる ====
def search_partner_info_by_keywords(user_message):
    try:
        values = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID3,  # 取引先情報
            range="取引先情報!A2:Z"
        ).execute().get("values", [])

        results = []
        for row in values:
            if any(user_message in cell for cell in row):
                results.append("📌[取引先] " + "｜".join(row))
        return "\n".join(results)
    except Exception as e:
        logging.error(f"取引先情報の検索失敗: {e}")
        return ""

# ==== キーワードから会話ログから情報を取ってくる ====
def search_log_sheets_by_keywords(user_message):
    try:
        values = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,  # 会話ログ
            range="会話ログ!A2:D"
        ).execute().get("values", [])

        results = []
        for row in values:
            if any(user_message in cell for cell in row):
                results.append("📌[会話ログ] " + "｜".join(row))
        return "\n".join(results)
    except Exception as e:
        logging.error(f"会話ログ検索失敗: {e}")
        return ""
        
# ==== キーワードから経験ログから情報を取ってくる ====
def search_experience_log_by_keywords(user_message):
    try:
        values = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range="経験ログ!A2:D"
        ).execute().get("values", [])
        results = []
        for row in values:
            if any(user_message in cell for cell in row):
                results.append("📌[経験ログ] " + "｜".join(row))
        return "\n".join(results)
    except Exception as e:
        logging.error(f"経験ログ検索失敗: {e}")
        return ""

# ==== 自動サマリー保存関数（毎日3時に実行） ====
def write_daily_summary():
    if not summary_log:
        return
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    all_text = "\n".join(summary_log)
    trimmed = all_text[:1900]  # 少し余裕をもって2000文字制限

    # ツンデレ愛子の気分別メッセージリスト
    closing_messages = [
        "……今日もよくがんばったのっ！（ドヤァ）",
        "ふん、別にサンネームのためにまとめたんじゃないんだからねっ！",
        "ちょっとだけ、やりきった気がするかも…なんてね♪",
        "これで明日もきっと大丈夫…だと思う、た、たぶんね",
        "やるじゃない、愛子。ちょっとだけ自分を褒めてあげたい",
        "今日は疲れたもうくったくたやねん",
        "明日もがんばるもん",
        "あーんもう嫌！誰かに癒されたい！",
        "今日もやりきったでござる"
    ]
    ending = random.choice(closing_messages)

    summary_text = f"愛子の日報（{date_str}）\n" + trimmed + f"\n{ending}"
    summary_log.clear()   #サマリーログをクリア
        
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

# ==== 自動実行スレッド ====
def daily_summary_scheduler():
    while True:
        now = now_jst()
        if now.hour == 3 and 0 <= now.minute < 5:
            summarize_daily_conversations()
            time.sleep(300)  # 5分待機（再実行防止）
        time.sleep(60)  # 1分ごとにチェック

# ==== 6時間ごとにブログの更新をチェック（ブログのタイトルが更新されていたら）してサマリーを記録する ====
def check_blog_updates():
    try:
        feed_url = "https://sun-name.com/bloglist/feed"  # RSSフィードURL
        feed = feedparser.parse(feed_url)
        existing_titles = get_read_titles_from_sheet()
        new_entries = []

        for entry in feed.entries:
            if entry.title not in existing_titles:
                new_entries.append(entry)
                register_blog_to_sheet(entry)

        if new_entries:
            logging.info(f"新しいブログ記事 {len(new_entries)} 件を会社情報に登録しました")
        else:
            logging.info("新しいブログ記事はありません")

    except Exception as e:
        logging.error(f"ブログチェック失敗: {e}")

# ==== ブログのタイトルをシートから読みだす ====
def get_read_titles_from_sheet():
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID4,
            range='会社情報!A2:Z'
        ).execute()
        rows = result.get("values", [])
        titles = [r[2] for r in rows if len(r) > 2 and r[0] == "ブログ更新"]
        return titles
    except Exception as e:
        logging.error(f"既読タイトルの取得失敗: {e}")
        return []

# ==== 自動実行スレッドにブログチェック追加 ====
def daily_summary_scheduler():
    while True:
        now = now_jst()
        if now.hour == 3 and 0 <= now.minute < 5:
            summarize_daily_conversations()
            time.sleep(300)
        if now.hour in [9, 13, 17, 21] and 0 <= now.minute < 5:
            check_blog_updates()
            time.sleep(300)
        time.sleep(60)
        
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

#LINE愛子botの返答を自然な日本語にするようにOpenAIに依頼
#個人情報と思われるパターンをマスクする（氏名・メール・電話番号など）
def mask_personal_info(text):
    text = re.sub(r'[\w.-]+@[\w.-]+', '[メールアドレス]', text)
    text = re.sub(r'\b\d{2,4}-\d{2,4}-\d{3,4}\b', '[電話番号]', text)
    text = re.sub(r'(さん|君|様)?[ \u4E00-\u9FFF]{2,4}(さん|君|様)?', '[氏名]', text)
    return text
    
#元の文章から、氏名・メール・電話番号を抽出し、マスク復元のための辞書を作成
def extract_original_terms(original_text):
    terms = {}
    name_match = re.search(r'[\u4E00-\u9FFF]{2,4}', original_text)
    if name_match:
        terms['[氏名]'] = name_match.group(0)
    email_match = re.search(r'[\w.-]+@[\w.-]+', original_text)
    if email_match:
        terms['[メールアドレス]'] = email_match.group(0)
    phone_match = re.search(r'\b\d{2,4}-\d{2,4}-\d{3,4}\b', original_text)
    if phone_match:
        terms['[電話番号]'] = phone_match.group(0)
    return terms

#OpenAIの返答に含まれるマスク語を、元の具体的な情報で置換して復元する
def restore_masked_terms(text, original_text):
    terms = extract_original_terms(original_text)
    for masked, real in terms.items():
        text = text.replace(masked, real)
    return text

# 個人情報は送らず、内容の要旨だけをOpenAIに伝えて丁寧で自然な日本語に整形された表現を取得する。
# その後、マスクされた語句を元の文から復元する。
def ask_openai_polite_rephrase(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは社内用のAIアシスタント愛子です。次のユーザーの発言を丁寧ながらも優秀でツンデレ気味の女の子風に言い換えてください。"
                        "これは情報提供の依頼ではなく、単なる言い換えのタスクです。"
                        "ユーザーの発言内容に対して時系列や学習データに関する回答は不要です。"
                        "内容は変えず、親しみやすいAI愛子らしい口調にしてください。返答は50文字以内で。"
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.warning(f"丁寧語変換失敗: {e}")
        return "すみません、言い換えに失敗しました。"

# 個人情報っぽいデータを全て抽出する。
def contains_personal_info(text):
    keywords = [
        "誕生日", "生年月日", "入社", "入社年", "住所", "電話", "家族",
        "名前", "氏名", "読み", "ふりがな", "携帯", "出身", "血液型",
        "メール", "メールアドレス", "年齢", "生まれ", "個人", "趣味", "特技"
    ]
    return any(keyword in text for keyword in keywords)

# 通常の会話はOpenAIにそのまま渡す。
def ask_openai_free_response(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.warning(f"OpenAI自由応答失敗: {e}")
        return "すみません、ちょっと考えがまとまりませんでした。"

    # 会話ログのF列（カテゴリー）をOpenAIに判定させる
    classify_message_context(user_message)

    elif user_expect_yes_no.get(user_id) == "await_specific_name":
        target_name = user_message.strip().replace("さん", "")
        matched_uid = None
        for uid, data in employee_info_map.items():
            if data.get("名前") == target_name or data.get("愛子ちゃんからの呼ばれ方") == target_name:
                matched_uid = uid
                break
        if matched_uid:
            user_expect_yes_no[user_id] = {
                "stage": "confirm_specific",
                "uids": [matched_uid],
                "names": [target_name],
                "message": last_user_message.get(user_id, '')
            }
            reply_text = f"{target_name}さんだけでいいですか？『はい』で送信、『いいえ』で他の方を追加します。"
        else:
            reply_text = f"⚠️『{target_name}』さんが見つかりませんでした。もう一度正確にお名前を教えてください。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        #log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        append_conversation_log(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        return

    elif isinstance(user_expect_yes_no.get(user_id), dict) and user_expect_yes_no[user_id].get("stage") == "confirm_specific":
        entry = user_expect_yes_no[user_id]
        if user_message.strip() == "はい":
            notify_text = f"📢 {user_name}さんよりご連絡です：『{entry['message']}』"
            for uid in entry["uids"]:
                line_bot_api.push_message(uid, TextSendMessage(text=notify_text))
            reply_text = "ご指定の方に送信しました。"
            user_expect_yes_no[user_id] = False
        elif user_message.strip() == "いいえ":
            reply_text = "他に伝える方のお名前を教えてください。"
            user_expect_yes_no[user_id] = entry | {"stage": "adding_more"}
        else:
            reply_text = "『はい』か『いいえ』で教えてください。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        #log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        append_conversation_log(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        return

    elif isinstance(user_expect_yes_no.get(user_id), dict) and user_expect_yes_no[user_id].get("stage") == "adding_more":
        entry = user_expect_yes_no[user_id]
        target_name = user_message.strip().replace("さん", "")
        matched_uid = None
        for uid, data in employee_info_map.items():
            if data.get("名前") == target_name or data.get("愛子ちゃんからの呼ばれ方") == target_name:
                matched_uid = uid
                break
        if matched_uid and matched_uid not in entry["uids"]:
            entry["uids"].append(matched_uid)
            entry["names"].append(target_name)
            reply_text = f"{target_name}さんを追加しました。他にもいますか？いなければ『はい』で送信、続けるなら名前を教えてください。"
        else:
            reply_text = f"⚠️『{target_name}』さんが見つからないか、すでに追加済みです。"
        user_expect_yes_no[user_id] = entry
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        #log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        append_conversation_log(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        return

    # 5. ユーザーの問いにマスクを付けてOpenAIに渡すかそのまま渡すかを分岐させ、マスクする場合はマスクしてOpenAIに丁寧語に変換する
    if contains_personal_info(user_message):
        masked_text = mask_personal_info(user_message)
        reply_text = ask_openai_polite_rephrase(masked_text)
        reply_text = restore_masked_terms(reply_text, user_message)
    else:
        reply_text = ask_openai_free_response(user_message)
        
    # 5. OpenAI に送信はしなくていい
    #messages = build_openai_messages(user_id, user_message) #OpenAIへのメッセージ
    #logging.info("OpenAI送信メッセージ:\n%s", user_message)
    #ai_reply = ask_openai_polite_rephrase(user_message)  # ← この行を追加
    #line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
    #log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
    #return

    # 5. AI応答のログ（SPREADSHEETの会話ログ）に保存
    append_log_conversation(
        timestamp=timestamp.isoformat(),
        user_id=user_id,
        user_name=user_name,
        speaker="AI",
        message=reply_text,
        status="愛子botから社内情報報告"
    )
    
    greeting = get_time_based_greeting()
    greeting_keywords = ["おっはー", "やっはろー", "おっつ〜", "ねむねむ"]
    ai_greeting_phrases = ["こんにちは", "こんにちわ", "おはよう", "こんばんは", "ごきげんよう", "お疲れ様", "おつかれさま"]

    # ログ保存：status="重要" を渡す
    #log_conversation(timestamp.isoformat(), user_id, user_name, "ユーザー", user_message, status="重要" if is_important else "OK")
    append_conversation_log(timestamp.isoformat(), user_id, user_name, "ユーザー", user_message, status="重要" if is_important else "OK")
            
    with cache_lock:
        user_recent = recent_user_logs.get(user_id, [])

    # 過去ログ（最大10件）の中から、同一のメッセージは1回だけ抽出し、GPTへのcontextに 重複メッセージを含まないようにする
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    context_entries = [row[4] for row in user_recent if len(row) >= 5]
    unique_entries = []

    if context_entries:
        vectorizer = TfidfVectorizer().fit(context_entries)
        vectors = vectorizer.transform(context_entries)
        seen_indices = []
        for i, vec in enumerate(vectors):
            is_similar = False
            for j in seen_indices:
                sim = cosine_similarity(vec, vectors[j])[0][0]
                if sim > 0.85:
                    is_similar = True
                    break
            if not is_similar:
                seen_indices.append(i)
                unique_entries.append(context_entries[i])

    context = "\n".join(unique_entries)

    # 経験ログ要約を文脈に加えOpenAIに伝える
    shared_summaries = get_recent_summaries()
    if shared_summaries:
        context = f"【愛子が学習した最近の知識】\n{shared_summaries}\n\n" + context
   
    # ユーザーの個別のログ要約を文脈に加えOpenAIに伝える
    user_summary = get_user_summary(user_id)
    if user_summary:
        context = f"【このユーザーの過去の要約情報】\n{user_summary}\n\n" + context

    #company_info_snippet = search_company_info_by_keywords(user_message, user_name, user_data)
    #if company_info_snippet:
    #    context += f"\n\n【会社情報データベースの参考回答】\n{company_info_snippet}\n"
    company_info_reply = search_company_info_by_keywords(user_message, user_name, user_data)
    if company_info_reply:
        context += f"\n\n【会社情報による参考情報】\n{company_info_reply}"

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


