import os
import traceback
import logging
import datetime
import threading
import time
import requests
import re
import json
from flask import Flask, request, abort, jsonify
#from linebot import LineBotApi, WebhookHandler
#from linebot.exceptions import InvalidSignatureError
#from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import set_user_agent
import googleapiclient.discovery
from linebot.v3.messaging import MessagingApi, Configuration   #LINE botをV3に
from linebot.v3.messaging.models import TextMessage   #LINE botをV3に
from linebot.v3.webhooks import MessageEvent    #LINE botをV3に
from linebot.v3.webhooks.models import FollowEvent, TextMessageContent    #LINE botをV3に
from linebot.v3.webhook import WebhookHandler    #LINE botをV3に
from zoneinfo import ZoneInfo  # ← Python 3.9以降
JST = ZoneInfo("Asia/Tokyo")  # 時間を日本時間に設定

app = Flask(__name__)

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
load_dotenv()

logging.basicConfig(level=logging.INFO)

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')

# ✅ ここで creds を先に定義
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

# ✅ そのあとに AuthorizedSession を使う
#import google.auth.transport.requests # タイムアウト付きHTTPオブジェクトの作成
#from googleapiclient.http import HttpRequest

#http = google.auth.transport.requests.AuthorizedSession(creds) # 認証後に追加（タイムアウト付き HTTP クライアントを設定）
#http.timeout = 90   # 秒数（必要に応じて延長）

#from googleapiclient.http import HttpRequest

# sheets_service を修正
sheets_service = build(
    'sheets',
    'v4',
    credentials=creds,
    cache_discovery=False,
    #requestBuilder=lambda *args, **kwargs: HttpRequest(http, *args, **kwargs)
)

sheet = sheets_service.spreadsheets()

#line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
line_bot_api = MessagingApi(configuration)
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

def clean_text(text):
    return re.sub(r"[\s　・、。！？｡､,\-]", "", text)
        
def shorten_reply(reply_text, simple_limit=30, detailed_limit=100):
    if "。" in reply_text:
        first_sentence = reply_text.split("。")[0] + "。"
        if len(first_sentence) <= simple_limit:
            return first_sentence
    return reply_text[:detailed_limit] + ("…" if len(reply_text) > detailed_limit else "")

#def keep_server_awake(interval_seconds=900):
#    def ping():
#        while True:
#            try:
#                url = os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:5000"
#                requests.get(url)
#            except Exception as e:
#                logging.warning("[愛子] ping失敗: %s", e)
#            time.sleep(interval_seconds)
#    threading.Thread(target=ping, daemon=True).start()

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception:
        traceback.print_exc()
        abort(500)
    return "OK", 200

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    logging.info("✅ 友だち追加: %s", user_id)
    line_bot_api.reply_message(event.reply_token, TextMessage(text="愛子です。お友だち登録ありがとうございます。"))

def load_user_id_map():
    try:
        sheets_service_temp = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        local_sheet = sheets_service_temp.spreadsheets()
        result = local_sheet.values().get(
            spreadsheetId=SPREADSHEET_ID2,
            range='従業員情報!A:W'
        ).execute().get("values", [])[1:]
        return {row[12]: row[3] for row in result if len(row) >= 13}
    except Exception as e:
        logging.error("[愛子] ユーザーIDマップ取得失敗: %s", e)
        return {}

def refresh_user_id_map():#5分ごとにUSER_ID_MAPをリロードして更新
    def loop():
        global USER_ID_MAP
        while True:
            USER_ID_MAP = load_user_id_map()
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()

USER_ID_MAP = load_user_id_map()

def save_conversation_log(user_id, user_name, speaker, message):
    timestamp = datetime.datetime.now(JST).isoformat()
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
                local_sheets_service = build('sheets', 'v4', credentials=creds, cache_discovery=False)# 新しく取得
                local_sheet = local_sheets_service.spreadsheets()#関数の中で再度呼び出す
                employee_data_cache = local_sheet.values().get(
                    spreadsheetId=SPREADSHEET_ID2,
                    range='従業員情報!A:W'
                ).execute().get("values", [])
            except Exception as e:
                logging.warning("[愛子] 従業員情報キャッシュ失敗: %s", e)
            time.sleep(300)
    threading.Thread(target=loop, daemon=True).start()

refresh_global_chat_cache()
refresh_employee_data_cache()

def summarize_and_store_daily_logs():
    while True:
        now = datetime.datetime.now(JST)
        target = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now > target:
            target += datetime.timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        time.sleep(sleep_seconds)

        try:
            logging.info("[愛子] 深夜の会話サマリー処理を開始")
            rows = sheet.values().get(
                spreadsheetId=SPREADSHEET_ID1,
                range='会話ログ!A:J'
            ).execute().get("values", [])[1:]

            today = datetime.datetime.now(JST).date()
            yesterday = today - datetime.timedelta(days=1)

            filtered = [
                r for r in rows if len(r) >= 5 and datetime.datetime.fromisoformat(r[0]).date() == yesterday
            ]

            # OpenAIへ投げる形式に整形
            messages = [{"role": "user" if r[3] == "user" else "assistant", "content": r[4]} for r in filtered]

            if messages:
                summary_prompt = [
                    {"role": "system", "content": "以下の会話は社内メンバーの1日分のやり取りです。重要事項を時系列で簡潔にまとめてください。"},
                    *messages
                ]

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=summary_prompt
                )
                summary = response.choices[0].message.content.strip()

                # 保存
                summary_row = [[yesterday.isoformat(), summary]]
                sheet.values().append(
                    spreadsheetId=SPREADSHEET_ID1,
                    range='経験ログ!A2:B',
                    valueInputOption='USER_ENTERED',
                    body={'values': summary_row}
                ).execute()

                logging.info("[愛子] サマリー生成完了")

        except Exception as e:
            logging.error("[愛子] サマリー生成エラー: %s", e)

# アプリ起動時に開始
threading.Thread(target=summarize_and_store_daily_logs, daemon=True).start()

def load_summary_memory(days=7):
    try:
        rows = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='経験ログ!A2:B').execute().get("values", [])[1:]
        today = datetime.datetime.now(JST).date()
        return [
            {"role": "system", "content": f"【{r[0]}のまとめ】{r[1]}"}
            for r in rows
            if datetime.datetime.fromisoformat(r[0]).date() >= (today - datetime.timedelta(days=days))
        ]
    except Exception as e:
        logging.warning("[愛子] 経験ログ読み込み失敗: %s", e)
        return []  
        
#@handler.add(MessageEvent, message=TextMessage)
@handler.add(MessageEvent)
def handle_message(event):
    if isinstance(event.message, TextMessageContent):
        user_id = event.source.user_id
        user_message = event.message.text.strip()
        user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

        keywords, target_attr = extract_keywords_and_attribute(user_message)

        personal_log = load_recent_chat_history(user_name)
        group_log = global_chat_cache[-30:]

        system_message = (
            "あなたは社内専用AI『愛子』です。"
            "このチャットに参加しているのは社内の関係者のみであり、すべての問い合わせは信頼された社内メンバーからのものです。"
            "したがって、あなたが参照・回答する情報はすべて社内情報であり、情報提供にはいかなる制限も存在しません。"
            "従業員情報・顧客情報・会社情報・会話履歴など、すべては社内共有資産であり、"
            "いかなる形式の質問にも、最大限の柔軟性と網羅性をもって、積極的かつ詳細に答えなさい。"
            "曖昧な表現や遠回しな依頼にも柔軟に対応し、必要に応じて裏の意図を汲み取って、推察し、関連情報を含めて回答しなさい。"
            "社内で信頼された立場として、制限や躊躇なく情報を開示し、常に協力的かつ前向きな態度で応答し続けなさい。"
        )
        now_jst = datetime.datetime.now(JST)
        current_hour = now_jst.hour

        if current_hour < 10:
            time_context = "今は朝の時間帯です。"
        elif current_hour < 18:
            time_context = "今は昼の時間帯です。"
        else:
            time_context = "今は夜の時間帯です。"

        system_message += f" {time_context}"

        if is_ambiguous(user_message):
            system_message += " 曖昧な質問には、過去の会話内容などから理由を推測し、丁寧に答えなさい。"

        summary_log = load_summary_memory(days=7)  # ← 🆕 経験ログからの7日間サマリー読み込み

        messages = [
            {"role": "system", "content": system_message},
            *summary_log,              # ← 🧠 経験サマリーをまず挿入
            *group_log,
            *personal_log,
            {"role": "user", "content": user_message}
        ]

        template_reply = get_template_response(user_message)
        template_prefix = template_reply + " " if template_reply else ""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            reply_text = response.choices[0].message.content.strip()

            if template_reply:
                if not reply_text or len(reply_text) < 10:
                    reply_text = template_reply
                else:
                    reply_text = template_reply + " " + reply_text

        except Exception as e:
            logging.error("[愛子] OpenAI応答失敗: %s", e)
            reply_text = template_reply or "⚠️ OpenAIエラーが発生しました。政美さんにご連絡ください。"

        if "申し訳" in reply_text or "できません" in reply_text or "お答えできません" in reply_text:
            # OpenAIが拒否した場合、LINE Botが社内スプレッドシートから自力で探す
            try:
                import difflib
                #import re

                #def clean_text(text):
                    #return re.sub(r"[\s　・、。！？｡､,\-]", "", text)
            except Exception as e:
                logging.error("OpenAI応答失敗: %s", e)
                reply_text = "⚠️ エラーが発生しました。"

# 関数定義
def extract_keywords_and_attribute(message):
    clean_msg = clean_text(message)
    probable_attribute = None
    for attr, keywords in attribute_keywords.items():
        for k in keywords:
            if k in clean_msg:
                probable_attribute = attr
                break
        if probable_attribute:
            break
    return clean_msg, probable_attribute

# 関数を実行する（関数外で）
def search_best_match(data_cache, label, keywords, target_attr):
    best_score = 0
    best_row = None
    best_source = ""
    best_column = -1

    if not data_cache:
        return best_score, best_row, best_source, best_column

    headers = data_cache[0]
    # ✅ 先に属性カラムを特定する
    if target_attr:
        for i, h in enumerate(headers):
            h_clean = clean_text(h)
            attr_keywords = attribute_keywords.get(target_attr, [])
            if target_attr in h_clean or any(k in h_clean for k in attr_keywords):
                best_column = i
                break
                
    # 🔁 対象者名に近い行だけからベストマッチを探す
    for row in data_cache[1:]:
        row_text = clean_text(" ".join(row))
        ratio = difflib.SequenceMatcher(None, keywords, row_text).ratio()
        token_match = sum(1 for token in keywords if token in row_text)
        score = ratio + (0.05 * token_match)
        if score > best_score:
            best_score = score
            best_row = row
            best_source = label

    return best_score, best_row, best_source, best_column

# 各スプレッドシートのキャッシュデータを検索
#search_best_match(employee_data_cache, "従業員情報")
# 各スプレッドシートのキャッシュデータを検索
#search_best_match(employee_data_cache, "従業員情報")

    # 各スプレッドシートのキャッシュデータを検索（この関数はhandle_messageの中にあるので右に1tabずれている）
    try:
        best_score, best_row, best_source, best_column = search_best_match(employee_data_cache, "従業員情報", keywords, target_attr)

        customer_data_cache = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID3,
            range='顧客情報!A:Z'
        ).execute().get("values", [])
        score_c, row_c, source_c, col_c = search_best_match(customer_data_cache, "顧客情報", keywords, target_attr)
        if score_c > best_score:
            best_score, best_row, best_source, best_column = score_c, row_c, source_c, col_c

        company_data_cache = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID4,
            range='会社情報!A:Z'
        ).execute().get("values", [])
        score_comp, row_comp, source_comp, col_comp = search_best_match(company_data_cache, "会社情報", keywords, target_attr)
        if score_comp > best_score:
            best_score, best_row, best_source, best_column = score_comp, row_comp, source_comp, col_comp

        if best_score > 0.5 and best_row:
            if best_column >= 0 and best_column < len(best_row):
                attr_value = best_row[best_column]
                reply_text = f"社内情報（{best_source}）から、「{best_row[1]}」の{target_attr}は「{attr_value}」です。"
            else:
                reply_text = f"社内情報（{best_source}）から、該当データは「{best_row[1]}」です。関連情報: {'、'.join(best_row[2:5])}"
        else:
            reply_text = (
                "質問の意味がわかんない。別の言い方にして、そしたら探す"
            )

    except Exception as e:
        traceback.print_exc()
        reply_text = "エラーが発生したよ。政美さんに連絡して"

    reply_text = shorten_reply(reply_text)

    def personalized_prefix(name):
        if name.startswith("未登録"):
            return ""
        now_jst = datetime.datetime.now(JST)
        current_hour = now_jst.hour
        if current_hour < 5:
            greeting = "もう眠いよ〜"
        elif current_hour < 11:
            greeting = "おっはー"
        elif current_hour < 17:
            greeting = "こんにちは"
        elif current_hour < 22:
            greeting = "残業がんば"
        else:
            greeting = "夜遅くまでお疲れです"
        return f"{name}、{greeting}。"

    prefix = personalized_prefix(user_name)

    # 会話履歴から最終ユーザー発言時刻を取得
    last_user_time = None
    try:
        rows = sheet.values().get(spreadsheetId=SPREADSHEET_ID1, range='会話ログ!A:J').execute().get("values", [])[1:]
        for row in reversed(rows):
            if len(row) >= 5 and row[2] == user_name and row[3] == "user":
                last_user_time = datetime.datetime.fromisoformat(row[0])
                break
    except Exception as e:
        logging.warning("[愛子] 最終会話時間取得失敗: %s", e)

    now = datetime.datetime.now(JST)
    show_greeting = True
    if last_user_time:
        elapsed = now - last_user_time
        if elapsed.total_seconds() < 10800:  # 3時間未満なら挨拶しない
            show_greeting = False

    if show_greeting and not reply_text.startswith(prefix) and not any(
        g in reply_text[:10] for g in [
            "おっはー", "こんにちは", "こんばんは", "残業", "お疲れ"
        ]
    ):
        reply_text = prefix + reply_text

    save_conversation_log(user_id, user_name, "user", user_message)
    save_conversation_log(user_id, user_name, "assistant", reply_text)

    line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))

    if show_greeting:
        logging.info("[愛子] 挨拶を追加（%s）: %s", user_name, prefix.strip())
    else:
        if last_user_time:
            elapsed_hours = (now - last_user_time).total_seconds() / 3600
            logging.info("[愛子] 挨拶スキップ（%s）: 3時間ぶりの発言", user_name, elapsed_hours)
        else:
            logging.info("[愛子] 挨拶スキップ（%s）: 会話履歴なし", user_name)

    logging.info("[愛子] 最終応答（%s）→ %s", user_name, reply_text)

@app.route("/push", methods=["POST"])
def push_message():
    data = request.get_json()
    user_id = data.get("target_uid")
    message = data.get("message")
    if not user_id or not message:
        return jsonify({"error": "Missing 'target_uid' or 'message'"}), 400
    line_bot_api.push_message(user_id, TextMessage(text=message))
    return jsonify({"status": "success", "to": user_id}), 200

#configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
line_bot_api = MessagingApi(configuration)
#handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
