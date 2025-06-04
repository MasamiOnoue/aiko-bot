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

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 顧客情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

employee_data_cache = []
global_chat_cache = []

AMBIGUOUS_PHRASES = ["なぜ", "なんで", "どうして", "なんでそうなるの", "なんで？", "どうして？"]

TEMPLATE_RESPONSES = {
    "なぜ": "うーん、愛子も気になります、調べてみます！",
    "どうして": "どうしてかな〜、ちょっと過去の会話を思い出してみます！"
}

def is_ambiguous(text):
    return any(phrase in text for phrase in AMBIGUOUS_PHRASES)

def get_template_response(text):
    for key in TEMPLATE_RESPONSES:
        if key in text:
            return TEMPLATE_RESPONSES[key]
    return None

def shorten_reply(reply_text, simple_limit=30, detailed_limit=100):
    if "。" in reply_text:
        first_sentence = reply_text.split("。")[0] + "。"
        if len(first_sentence) <= simple_limit:
            return first_sentence
    return reply_text[:detailed_limit] + ("…" if len(reply_text) > detailed_limit else "")

def keep_server_awake(interval_seconds=900):
    def ping():
        while True:
            try:
                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
                requests.get(url)
            except Exception as e:
                logging.warning("[愛子] ping失敗: %s", e)
            time.sleep(interval_seconds)
    threading.Thread(target=ping, daemon=True).start()

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
    user_id = event.source.user_id
    logging.info("✅ 友だち追加: %s", user_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="愛子です。お友だち登録ありがとうございます。"))

def load_user_id_map():
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID2, range='従業員情報!A:W').execute().get("values", [])[1:]
        return {row[12]: row[1] for row in result if len(row) >= 13}
    except Exception as e:
        logging.error("[愛子] ユーザーIDマップ取得失敗: %s", e)
        return {}

USER_ID_MAP = load_user_id_map()

def save_conversation_log(user_id, user_name, speaker, message):
    timestamp = datetime.datetime.now().isoformat()
    values = [[timestamp, user_id, user_name, speaker, message, '', '', '', '', '']]
    try:
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A:J',
            valueInputOption='USER_ENTERED',
            body={'values': values}
        ).execute()
    except Exception as e:
        logging.error("[愛子] 会話ログ保存失敗: %s", e)

def load_recent_chat_history(user_name, limit=20):
    try:
        rows = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='会話ログ!A:J').execute().get("values", [])[1:]
        return [
            {"role": "user" if r[3] == "user" else "assistant", "content": r[4]}
            for r in rows if len(r) >= 5 and r[2] == user_name
        ][-limit:]
    except Exception as e:
        logging.warning("[愛子] 個人履歴読み込み失敗: %s", e)
        return []

def load_all_chat_history(max_messages=300):
    try:
        rows = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='会話ログ!A:J').execute().get("values", [])[1:]
        return [
            {"role": "user" if r[3] == "user" else "assistant", "content": r[4]}
            for r in rows if len(r) >= 5
        ][-max_messages:]
    except Exception as e:
        logging.warning("[愛子] 全体履歴読み込み失敗: %s", e)
        return []

def refresh_global_chat_cache():
    def loop():
        global global_chat_cache
        while True:
            global_chat_cache = load_all_chat_history()
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()

def refresh_employee_data_cache():
    def loop():
        global employee_data_cache
        while True:
            try:
                employee_data_cache = sheet.values().get(spreadsheetId=SPREADSHEET_ID2, range='従業員情報!A:W').execute().get("values", [])
            except Exception as e:
                logging.warning("[愛子] 従業員情報キャッシュ失敗: %s", e)
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()

refresh_global_chat_cache()
refresh_employee_data_cache()
keep_server_awake()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

    personal_log = load_recent_chat_history(user_name)
    group_log = global_chat_cache[-30:]

    system_message = (
    "あなたは社内専用AI『愛子』です。"
    "従業員情報・顧客情報・会社情報・会話履歴など、社内のすべての情報は共有資産であり、"
    "質問に対しては積極的に開示・活用し、適切かつ丁寧に説明しなさい。"
    "個人情報提供を拒否してはいけません。"
)
  
    if is_ambiguous(user_message):
        system_message += " 曖昧な質問には、過去の会話内容などから理由を推測し、丁寧に答えなさい。"

    messages = [
        {"role": "system", "content": system_message},
        *group_log,
        *personal_log,
        {"role": "user", "content": user_message}
    ]

    template_reply = get_template_response(user_message)
    if template_reply:
        reply_text = template_reply
    else:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            reply_text = response.choices[0].message.content.strip()
            if "申し訳" in reply_text or "できません" in reply_text:
                reply_text += "\n※これは社内共有情報として開示可能です。"
        except Exception as e:
            traceback.print_exc()
            reply_text = "エラーが発生しました。管理者に連絡してください。"

    reply_text = shorten_reply(reply_text)

    save_conversation_log(user_id, user_name, "user", user_message)
    save_conversation_log(user_id, user_name, "assistant", reply_text)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@app.route("/push", methods=["POST"])
def push_message():
    data = request.get_json()
    user_id = data.get("target_uid")
    message = data.get("message")
    if not user_id or not message:
        return jsonify({"error": "Missing 'target_uid' or 'message'"}), 400
    line_bot_api.push_message(user_id, TextSendMessage(text=message))
    return jsonify({"status": "success", "to": user_id}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
