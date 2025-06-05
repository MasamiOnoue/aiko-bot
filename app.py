import os
import traceback
import logging
import datetime
import threading
import time
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

app = Flask(__name__)

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
conversation_cache = []
last_cache_update_time = datetime.datetime.min

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheet_service = build('sheets', 'v4', credentials=credentials)
sheet = sheet_service.spreadsheets()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

attribute_keywords = {
    "名前": ["名前", "氏名"],
    "名前の読み": ["名前の読み", "読み", "よみ"],
    "役職": ["役職", "肩書", "ポスト", "仕事", "役割"],
    "入社年": ["入社年", "入社", "最初の年"],
    "生年月日": ["生年月日", "生まれ", "誕生日", "バースデー"],
    "メールアドレス": ["メールアドレス", "メール", "e-mail", "連絡", "アドレス", "メアド"],
    "携帯電話番号": ["携帯電話番号", "携帯", "携帯番号", "携帯電話", "電話番号", "携帯は", "携帯番号は", "携帯電話番号は", "連絡先"],
    "自宅電話": ["自宅電話", "電話", "番号", "電話番号", "自宅の電"],
    "住所": ["住所", "所在地", "場所", "どこ"],
    "郵便番号": ["郵便番号", "〒", "郵便"],
    "緊急連絡先": ["緊急連絡先", "緊急", "問い合わせ先", "至急連絡"],
    "ペット情報": ["ペット情報", "犬", "猫", "いぬ", "イヌ", "ネコ", "ねこ", "にゃんこ", "わんちゃん", "わんこ"],
    "性格": ["性格", "大人しい", "うるさい", "性質", "特性"],
    "口癖": ["口癖", "よく言う", "よく語る", "軟着陸"],
    "備考": ["備考", "その他"],
    "追加情報": ["追加情報", "部署", "部門", "部"],
    "家族": ["家族", "配偶者", "妻", "夫", "子供", "扶養", "ペット", "犬", "猫", "いぬ", "ねこ", "わんちゃん"]
}

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
        employee = employee_info_map.get(user_id, {})
        nickname = employee.get("愛子からの呼ばれ方", "")
        values = [[
            timestamp,
            user_id,
            nickname,
            speaker,
            message,
            "未分類",
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

def search_employee_info_by_keywords(query):
    words = query.split()
    matches = {}
    for column, keywords in attribute_keywords.items():
        for keyword in keywords:
            if any(keyword in word for word in words):
                matches[column] = True
                break

    results = []
    for data in employee_info_map.values():
        for column in matches:
            if column in data:
                results.append(f"{column}: {data[column]}")
        if results:
            return "🔎 社内情報から見つけました: " + ", ".join(results)

    return "⚠️ 社内情報でも見つかりませんでした。"

def update_caches():
    global last_cache_update_time, conversation_cache, employee_info_map
    try:
        now = datetime.datetime.now()
        if (now - last_cache_update_time).seconds > 300:
            emp_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID2, range='従業員情報!A:Y').execute().get("values", [])
            headers = emp_data[0]
            for row in emp_data[1:]:
                uid = row[13] if len(row) > 13 else None
                if uid:
                    employee_info_map[uid] = dict(zip(headers, row))

            conv_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='会話ログ!A:J').execute().get("values", [])
            conversation_cache = conv_data[-100:]
            last_cache_update_time = now
    except Exception as e:
        logging.error("キャッシュ更新失敗: %s", e)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    update_caches()
    user_id = event.source.user_id
    user_message = event.message.text
    timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S")
    user_name = employee_info_map.get(user_id, {}).get("名前", "不明")
    nickname = employee_info_map.get(user_id, {}).get("愛子からの呼ばれ方", "")
    greeting = get_time_based_greeting()

    # 直近のユーザー発言を10件取得
    recent_logs = []
    try:
        logs = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A:J'
        ).execute().get("values", [])
        recent_logs = [log for log in reversed(logs) if len(log) > 1 and log[1] == user_id and log[3] == "ユーザー"][:10]
    except Exception as e:
        logging.warning("最新会話ログ取得失敗: %s", e)

    log_conversation(timestamp, user_id, user_name, "ユーザー", user_message)

    try:
        openai = OpenAI()
        messages = [{"role": "system", "content": "あなたは社内サポートAIです。挨拶は繰り返さず、適切に対応してください。"}]

        for log in reversed(recent_logs):
            messages.append({"role": "user", "content": log[4]})

        messages.append({"role": "user", "content": user_message})

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        reply_content = response.choices[0].message.content.strip()
        if any(word in reply_content for word in ["申し訳", "できません"]):
            reply_text = search_employee_info_by_keywords(user_message)
        else:
            reply_text = greeting + nickname + "、" + reply_content
    except Exception as e:
        logging.error("OpenAI呼び出し失敗: %s", e)
        reply_text = search_employee_info_by_keywords(user_message)

    log_conversation(timestamp, user_id, user_name, "愛子", reply_text)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
