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
experience_cache = []
client_cache = []
company_cache = []
last_cache_update_time = datetime.datetime.min
last_experience_cache_time = datetime.datetime.min
last_client_cache_time = datetime.datetime.min
last_company_cache_time = datetime.datetime.min

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

def update_caches():
    global last_cache_update_time, last_experience_cache_time, last_client_cache_time, last_company_cache_time
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
            conversation_cache[:] = conv_data[-100:]
            last_cache_update_time = now

        if (now - last_experience_cache_time).seconds > 1800:
            exp_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID5, range='経験ログ!B:B').execute().get("values", [])
            experience_cache[:] = exp_data[-20:]
            last_experience_cache_time = now

        if (now - last_client_cache_time).seconds > 1800:
            client_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID3, range='取引先情報!A:Z').execute().get("values", [])
            client_cache[:] = client_data
            last_client_cache_time = now

        if (now - last_company_cache_time).seconds > 1800:
            company_data = sheet.values().get(spreadsheetId=SPREADSHEET_ID4, range='会社ノウハウ情報!A:Z').execute().get("values", [])
            company_cache[:] = company_data
            last_company_cache_time = now

    except Exception as e:
        logging.error("キャッシュ更新失敗: %s", e)

def summarize_daily_logs():
    try:
        today = now_jst().date()
        yesterday = today - datetime.timedelta(days=1)
        logs = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='会話ログ!A:J').execute().get("values", [])
        target_logs = [log[4] for log in logs if len(log) > 4 and log[0].startswith(str(yesterday))]

        if not target_logs:
            return

        openai = OpenAI()
        messages = [
            {"role": "system", "content": "以下は社内AI愛子の前日の会話ログです。内容を要約して最大限の情報を抽出してください。"},
            {"role": "user", "content": "
".join(target_logs)}
        ]
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        summary = response.choices[0].message.content.strip()
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID5,
            range='経験ログ!B:B',
            valueInputOption='USER_ENTERED',
            body={'values': [[summary]]}
        ).execute()
        logging.info("前日サマリーを保存しました。")
    except Exception as e:
        logging.error("サマリー生成失敗: %s", e)

def schedule_summary():
    while True:
        now = now_jst()
        if now.hour == 3 and now.minute < 5:
            summarize_daily_logs()
        time.sleep(300)

threading.Thread(target=schedule_summary, daemon=True).start()

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

    recent_logs = []
    try:
        logs = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range='会話ログ!A:J'
        ).execute().get("values", [])
        recent_logs = [log for log in reversed(logs) if len(log) > 1 and log[1] == user_id and log[3] == "ユーザー"][:10]
    except Exception as e:
        logging.warning("最新会話ログ取得失敗: %s", e)

    try:
        openai = OpenAI()
        messages = [
            {"role": "system", "content": "あなたは社内サポートAIです。経験ログ、取引先情報、会社情報を参考に、簡潔で丁寧な回答をしてください。挨拶は繰り返さないように注意してください。"}
        ]

        for row in experience_cache:
            if row:
                messages.append({"role": "system", "content": row[0]})
        for row in client_cache[:5]:
            messages.append({"role": "system", "content": ", ".join(row)})
        for row in company_cache[:5]:
            messages.append({"role": "system", "content": ", ".join(row)})

        for log in reversed(recent_logs):
            messages.append({"role": "user", "content": log[4]})

        messages.append({"role": "user", "content": user_message})

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        reply_content = response.choices[0].message.content.strip()

        if any(word in reply_content for word in ["申し訳", "できません"]):
            if "愛子" in user_message:
                reply_text = f"{nickname}、何かご用でしょうか？"
            else:
                reply_text = "社内情報でも見つかりませんでした。"
        else:
            reply_text = greeting + nickname + "、" + reply_content

    except Exception as e:
        logging.error("OpenAI呼び出し失敗: %s", e)
        reply_text = "社内情報でも見つかりませんでした。"

    values = [[timestamp, user_id, nickname, "ユーザー", user_message, "未分類", "text", "", "OK", ""]]
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID1,
        range='会話ログ!A:J',
        valueInputOption='USER_ENTERED',
        body={'values': values}
    ).execute()

    values = [[timestamp, user_id, nickname, "愛子", reply_text, "未分類", "text", "", "OK", ""]]
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID1,
        range='会話ログ!A:J',
        valueInputOption='USER_ENTERED',
        body={'values': values}
    ).execute()

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )



    )

# Flaskアプリ起動判定（この中には実処理を置かない）
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
