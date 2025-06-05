import os
import traceback
import logging
import datetime
import threading
import time
import re
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz

load_dotenv()

# 日本標準時 (JST) タイムゾーン
JST = pytz.timezone('Asia/Tokyo')

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社ノウハウ情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験サマリー記録

cache_lock = threading.Lock()
recent_user_logs = {}
employee_info_map = {}
last_greeting_time = {}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

def now_jst():
    return datetime.datetime.now(JST)

def get_time_based_greeting():
    hour = now_jst().hour
    if 5 <= hour < 10:
        return "おっはー。"
    elif 10 <= hour < 18:
        return "やっはろー。"
    elif 18 <= hour < 23:
        return "おっつ〜。"
    else:
        return "ねむねむ。"

def log_conversation(timestamp, user_id, user_name, speaker, message, status="OK"):
    try:
        values = [[
            timestamp,
            user_id,
            user_name or "不明",
            speaker,
            message,
            "重要" if status == "重要" else "未分類",  # ← ここで重要を反映
            "text",
            "",
            status,
            ""
        ]]
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A:J',
            valueInputOption='USER_ENTERED',
            body={'values': values}
        ).execute()
    except Exception as e:
        logging.error("ログ保存失敗: %s", e)
        
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
            range='従業員情報!A1:Z'
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

SPREADSHEET_IDS = [
    SPREADSHEET_ID1,
    SPREADSHEET_ID2,
    SPREADSHEET_ID3,
    SPREADSHEET_ID4,
    SPREADSHEET_ID5
]

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

def search_employee_info_by_keywords(query):
    keywords = query.split()
    for data in employee_info_map.values():
        if any(k in str(data.values()) for k in keywords):
            return "🔎 社内情報から見つけました: " + ", ".join(f"{k}: {v}" for k, v in data.items())
    return "⚠️ 社内情報でも見つかりませんでした。"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    timestamp = now_jst()
    user_data = employee_info_map.get(user_id, {})
    user_name = user_data.get("名前", "")
    important_keywords = ["覚えておいて", "おぼえておいて", "覚えてね", "記録して", "メモして"]
    is_important = any(kw in user_message for kw in important_keywords)

    # タグ分類の簡易抽出（#タグ名形式を想定）
    tags = re.findall(r"#(\w+)", user_message)
    tag_str = ", ".join(tags) if tags else "未分類"

    # ノウハウ記録：重要なメッセージは会社ノウハウへも保存
    if is_important:
        try:
            knowledge_values = [[
                timestamp.isoformat(),
                user_id,
                user_name,
                user_message,
                tag_str  #情報タグ
            ]]
            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID4,
                range='会社ノウハウ!A:E',
                valueInputOption='USER_ENTERED',
                body={'values': knowledge_values}
            ).execute()
         except Exception as e:
            logging.error("ノウハウ記録失敗: %s", e)

    # ノウハウ確認要求があるかチェック
    confirm_knowledge_keywords = ["覚えた内容を確認", "ノウハウを確認", "記録した内容を見せて"]
    if any(k in user_message for k in confirm_knowledge_keywords):
        try:
            result = sheet.values().get(
                spreadsheetId=SPREADSHEET_ID4,
                range='会社ノウハウ!A2:E'
            ).execute()
            rows = result.get("values", [])[-5:]  # 最新5件のみ
            if rows:
                reply_text = "📘最近の記録内容:\n" + "\n".join(f"・{r[3]} ({r[2]})【{r[4] if len(r) > 4 else 'タグなし'}】" for r in rows if len(r) >= 4)
            else:
                reply_text = "📘まだノウハウは記録されていません。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return
        except Exception as e:
            logging.error("ノウハウ取得失敗: %s", e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ ノウハウの取得に失敗しました。"))
            return

    greeting = get_time_based_greeting()
    greeting_keywords = ["おっはー", "やっはろー", "おっつ〜", "ねむねむ"]
    ai_greeting_phrases = ["こんにちは", "こんにちわ", "おはよう", "こんばんは", "ごきげんよう", "お疲れ様", "おつかれさま"]

    # ログ保存：status="重要" を渡す
    log_conversation(timestamp.isoformat(), user_id, user_name, "ユーザー", user_message, status="重要" if is_important else "OK")
            
    with cache_lock:
        user_recent = recent_user_logs.get(user_id, [])

    context = "\n".join(row[4] for row in user_recent if len(row) >= 5)

    # 最後の挨拶から2時間以内なら greeting を削除
    show_greeting = True
    if user_id in last_greeting_time:
        elapsed = (timestamp - last_greeting_time[user_id]).total_seconds()
        if elapsed < 7200:
            show_greeting = False
    if show_greeting:
        last_greeting_time[user_id] = timestamp

    # ユーザーの発言にすでに挨拶が含まれているかチェック
    if any(g in user_message for g in greeting_keywords + ai_greeting_phrases):
        show_greeting = False

    messages = [
        {"role": "system", "content": (
            "あなたは社内アシスタントAI『愛子』です。次のルールを守ってください。\n"
            "・最初の挨拶はユーザーがしていれば繰り返さない。\n"
            "・挨拶メッセージ（例:やっはろー）は30文字以内に。\n"
            "・質問回答などは丁寧に100文字程度で。"
        )},
        {"role": "user", "content": context + "\n" + user_message}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        reply_text = response.choices[0].message.content.strip()

        if reply_text.startswith("申し訳") or reply_text.startswith("できません"):
            fallback = search_employee_info_by_keywords(user_message)
            if "見つかりました" in fallback:
                reply_text += "\n\n" + fallback

        if show_greeting and not any(reply_text.startswith(g) for g in greeting_keywords + ai_greeting_phrases):
            reply_text = f"{greeting}{user_name}。" + reply_text

    except Exception as e:
        logging.error("OpenAI 応答失敗: %s", e)
        reply_text = "⚠️ 応答に失敗しました。政美さんにご連絡ください。"

    log_conversation(now_jst().isoformat(), user_id, user_name, "AI", reply_text)
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
