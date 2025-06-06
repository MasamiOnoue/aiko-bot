import os
import traceback
import logging
import datetime
import threading
import time
import json
import re
import feedparser #ブログチェック機能
import pytz
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging  #通信ログをRenderに出力するようにする

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

# 日本標準時 (JST) タイムゾーン
JST = pytz.timezone('Asia/Tokyo')

SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

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

# ==== 会社情報スプレッドシートの列構成定義 ====
COMPANY_INFO_COLUMNS = {
    "カテゴリ": 0,
    "キーワード": 1,
    "質問例": 2,
    "回答内容": 3,
    "回答要約": 4,
    "補足情報": 5,
    "最終更新日": 6,
    "登録者名": 7,
    "使用回数": 8,
    "担当者": 9,
    "開示範囲": 10,
    "予備2": 11,
    "予備3": 12,
    "予備4": 13,
    "予備5": 14,
    "予備6": 15,
    "予備7": 16,
    "予備8": 17,
    "予備9": 18,
    "予備10": 19,
    "予備11": 20,
    "予備12": 21,
    "予備13": 22,
    "予備14": 23,
    "予備15": 24,
    "予備16": 25
}

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
    
# 愛子の経験ログ＝つまり日記の情報を読み込む
def get_recent_summaries(count=5):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID5,
            range='経験ログ!A2:C'
        ).execute()
        rows = result.get("values", [])[-count:]
        return "\n".join(f"【{r[2]}】{r[3]}" for r in rows if len(r) >= 4)
    except Exception as e:
        logging.error(f"全体の経験ログ取得失敗: {e}")
        return ""
        
# 会話ログの情報を保存する関数       
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
            range='従業員情報!A2:Z'
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

#キーワードから従業員情報をSPREADSHEETから持ってくる専用関数
def search_employee_info_by_keywords(query):
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

    result_texts = []
    lowered_query = query.lower()
    for uid, data in employee_info_map.items():
        for attr, keywords in attribute_keywords.items():
            for keyword in keywords:
                if keyword.lower() in lowered_query:
                    value = data.get(attr) or data.get(attr.replace("携帯電話番号", "携帯番号"))
                    if not value:
                        continue  # 値が存在しない場合はスキップ
                    if attr not in data:
                        continue  # 無効なキーが含まれている場合もスキップ
                    result_texts.append(f"📌 {data.get('名前', '不明')}の{attr}は「{value}」です。")
    # 🔁 fallback検索のため、result_textsが空でもreturnしない
    if result_texts:
        return "\n".join(result_texts)

    # fallback検索（曖昧一致）
    keywords = query.split()
    for data in employee_info_map.values():
        if any(k in str(data.values()) for k in keywords):
            return "🔎 社内情報から見つけました: " + ", ".join(f"{k}: {v}" for k, v in data.items())

    return "⚠️ 社内情報でも見つかりませんでした。"

# ==== 自動日記をOpenAIにやらせる関数（毎日3時に呼び出す） ====
def generate_daily_summaries(logs_by_user, sheet, client, SPREADSHEET_ID5):
    for (uid, name), messages in logs_by_user.items():
        context = "\n".join(messages)
        prompt = [
            {"role": "system", "content": (
                "あなたはLINEで社員と日々会話しているAIアシスタント『愛子』です。\n"
                "以下はあなたが昨日、社員と交わした会話の記録です。\n"
                "感情・思考・行動・課題・印象などを踏まえ、社員とのやり取りを振り返る日記として"
                "自分の目線で2000文字以内で自然に要約してください。\n"
                "主語は『私』を用い、社員を『○○さん』などと呼び、第三者視点ではなく主観的に書いてください。\n"
                "また、要約文中に改行は使用せず、すべての内容を削除せずに情報を圧縮して簡潔に記述してください。"
            )},
            {"role": "user", "content": context}
        ]
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=prompt,
                max_tokens=800
            )
            summary = response.choices[0].message.content.strip().replace("\n", " ")  # 改行除去
            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID5,
                range='経験ログ!A:B',
                valueInputOption='USER_ENTERED',
                body={'values': [[now_jst().isoformat(), summary]]}
            ).execute()
            logging.info(f"{name} の要約を保存しました")
        except Exception as e:
            logging.error(f"{name} の要約失敗: {e}")

# ==== 自動日記要約（毎日3時に実行） ====
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
        generate_daily_summaries(logs_by_user, sheet, client, SPREADSHEET_ID5)

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
            range='経験ログ!A:B'
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

# ==== ブログの内容を要約して会社情報に更新する ====
def register_blog_to_sheet(entry):
    try:
        values = [[
            "ブログ更新",          # カテゴリ
            entry.link,          # URL
            entry.title,         # タイトル
            entry.summary[:100],# 要約
            entry.published,     # 日付
            "自動取得",         # 補足情報
            now_jst().strftime("%Y-%m-%d"),
            "システム",
            0,
            "愛子"
        ] + [""] * 16]

        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID4,
            range='会社情報!A2:Z',
            valueInputOption='USER_ENTERED',
            body={'values': values}
        ).execute()

    except Exception as e:
        logging.error(f"ブログ記事の登録失敗: {e}")

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
def ask_openai_polite_rephrase(original_text, model="gpt-4o", temperature=0.5, max_tokens=100):
    try:
        masked_text = mask_personal_info(original_text)
        prompt = (
            f"丁寧で自然な日本語に言い換えてください：\n\n{masked_text}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        reply = response.choices[0].message.content.strip()
        
        # 返答が不自然に重複していた場合、2行目以降を除去
        lines = reply.split("\n")
        if len(lines) > 1 and lines[0] == lines[1]:
            reply = lines[0]
            
        # マスクされた語句を復元
        return restore_masked_terms(reply, original_text)

    except Exception as e:
        logging.error(f"OpenAI 応答失敗: {e}")
        return "⚠️ 応答に失敗しました。しばらくしてからもう一度お試しください。"

# 削除対象の語句（すべて「覚えて系」）
def clean_log_message(text):
    patterns = [
        "覚えてください", "覚えて", "おぼえておいて", "覚えてね",
        "記録して", "メモして", "忘れないで", "記憶して",
        "保存して", "記録お願い", "記録をお願い"
    ]
    # パターンを1つの正規表現にまとめて削除（どれか1つにマッチすれば削除）
    pattern = "|".join(map(re.escape, patterns))
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        
#  ==== メインのLINEから受信が来た時のメッセージ処理のメインルーチン ==== 
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    timestamp = now_jst()
    user_data = employee_info_map.get(user_id, {})
    user_name = user_data.get("愛子ちゃんからの呼ばれ方", user_data.get("名前", ""))
    important_keywords = ["覚えておいて", "おぼえておいて", "覚えてね", "記録して", "メモして", "覚えてください", "覚えて", "忘れないで", "記憶して", "保存して", "記録お願い", "記録をお願い"]
    is_important = any(kw in user_message for kw in important_keywords)
    experience_context = get_recent_experience_summary(sheet, user_name)

    # 1. user_name空文字だった場合、LINEのプロフィールから取得
    if not user_name:
    try:
        profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception as e:
        logging.warning(f"ユーザー名の取得に失敗しました: {e}")
        user_name = "未登録ユーザー"

    # 2. 会社情報を優先してチェック
    company_info_reply = search_company_info_by_keywords(user_message, user_name, user_data)
    if company_info_reply:
        prompt = f"社内情報に基づいて、質問『{user_message}』に丁寧に日本語で答えてください。\n\n社内情報:\n{company_info_reply}"
        ai_reply = ask_openai_polite_rephrase(prompt)
        #ai_reply = ask_openai_polite_rephrase(original_text, model="gpt-4o", temperature=0.5, max_tokens=100):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
        log_conversation(timestamp.isoformat(), user_id, user_name, "AI", ai_reply)
        return

    # 3. 従業員情報もチェック
    employee_info_reply = search_employee_info_by_keywords(user_message)
    if "📌" in employee_info_reply:
        prompt = f"従業員情報に基づいて、質問『{user_message}』に答えてください。\n\n従業員情報:\n{employee_info_reply}"
        ai_reply = ask_openai_polite_rephrase(prompt)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
        log_conversation(timestamp.isoformat(), user_id, user_name, "AI", ai_reply)
        return

    # 4. OpenAI に送信
    #messages = build_openai_messages(user_id, user_message) #OpenAIへのメッセージ
    logging.info("OpenAI送信メッセージ:\n%s", user_message)
    ai_reply = ask_openai_polite_rephrase(user_message)  # ← この行を追加
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_reply))
    log_conversation(timestamp.isoformat(), user_id, user_name, "AI", ai_reply)
        
    # デバッグ用。employee_info_mapをRenderログに出力
    #logging.info("🔥 employee_info_map の内容確認開始")
    #try:
    #    logging.info("employee_info_map:\n%s", json.dumps(employee_info_map, ensure_ascii=False, indent=2))
    #except Exception as e:
    #    logging.warning("employee_info_map のログ出力に失敗しました: %s", str(e))
    
    # 5. メッセージから「他の人に伝える」意図があるか判定。対象が「全員」か「特定の相手」かを確認。対象に通知を送信
    bridge_keywords = ["伝えて", "知らせて", "連絡して", "お知らせして", "休みます", "遅れます"]
    
    #if any(kw in user_message for kw in bridge_keywords):
    #    ask_text = "この内容を全員にお知らせしますか？それとも、誰か特定の方にだけ伝えますか？"
    #    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ask_text))
    #    log_conversation(timestamp.isoformat(), user_id, user_name, "AI", ask_text)

    # 6. 社内情報は常時、先にキーワードを探すようする
    company_info_reply = search_company_info_by_keywords(user_message, user_name, user_data)
    reply_text = ""
    if company_info_reply:
        reply_text = company_info_reply
        # LINEに直接返して return する（OpenAIをバイパス）
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return
    
    if "全員に" in user_message:
        notify_text = f"📢 {user_name}さんよりご連絡です：『{user_message}』"
        for uid, data in employee_info_map.items():
            if uid != user_id:
                try:
                    line_bot_api.push_message(uid, TextSendMessage(text=notify_text))
                except Exception as e:
                    logging.error(f"通知失敗: {uid} - {e}")
        reply_text = "みなさんにお知らせしました。"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        return

    match = re.search(r"(\S+?)(?:さん)?だけに伝えて", user_message)
    if match:
        target_name = match.group(1)
        notify_text = f"📢 {user_name}さんよりご連絡です：『{user_message}』"
        for uid, data in employee_info_map.items():
            if data.get("名前") == target_name or data.get("愛子ちゃんからの呼ばれ方") == target_name:
                try:
                    line_bot_api.push_message(uid, TextSendMessage(text=notify_text))
                    reply_text = f"{target_name}にだけお伝えしました。"
                    break
                except Exception as e:
                    logging.error(f"通知失敗: {uid} - {e}")
                    reply_text = f"⚠️ {target_name}への通知に失敗しました。"
                    break
        else:
            reply_text = f"⚠️ お名前が『{target_name}』の方が見つかりませんでした。"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        log_conversation(timestamp.isoformat(), user_id, user_name, "AI", reply_text)
        return
        
    # タグ分類の簡易抽出（#タグ名形式を想定）
    tags = re.findall(r"#(\w+)", user_message)
    tag_str = ", ".join(tags) if tags else "未分類"

    # ノウハウ記録：重要なメッセージは会社情報へも保存
    if is_important:
        try:
            knowledge_values = [[
                "会話メモ",                          # A: カテゴリ
                "なし",                              # B: キーワード
                user_message[:20],                  # C: 質問例（20文字程度）
                user_message,                       # D: 回答内容
                user_message[:50],                  # E: 回答要約（50文字程度）
                "LINEから記録",                     # F: 補足情報
                now_jst().strftime("%Y-%m-%d"),     # G: 最終更新日
                "愛子",                             # H: 登録者名
                0,                                  # I: 使用回数
                name,                               # J: 担当者
                "社内"                             # K: 開示範囲
            ] + [""] * 14]  # K〜Z: 予備を空で埋める（列Zまで14列必要）

            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID4,
                range='会社情報!A2:Z',
                valueInputOption='USER_ENTERED',
                body={'values': knowledge_values}
            ).execute()
        except Exception as e:
            logging.error("会社ノウハウへ記録失敗: %s", e)

    # ノウハウ確認要求があるかチェック
    confirm_knowledge_keywords = ["覚えた内容を確認", "ノウハウを確認", "記録した内容を見せて"]
    if any(k in user_message for k in confirm_knowledge_keywords):
        try:
            result = sheet.values().get(
                spreadsheetId=SPREADSHEET_ID4,
                range='会社情報!A2:Z'
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
    show_greeting = True    # 最初に show_greeting フラグを True にしておく

    # 1. ユーザー発言にすでに挨拶が含まれていれば、挨拶しない
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

    # ユーザーの発言にすでに挨拶が含まれているかチェック
    if any(g in user_message for g in greeting_keywords + ai_greeting_phrases):
        show_greeting = False

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
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        # AIによる返答取得
        reply_text = response.choices[0].message.content.strip()
        logging.info("OpenAI送信メッセージ:\n%s", messages)  # ロギング用
        logging.info("🧠 OpenAI応答:\n%s", reply_text)  # ロギング用
        
        # ここで会社情報からの追記を実施
        #company_info_reply = search_company_info_by_keywords(user_message)
        #if company_info_reply:
        #    reply_text += f"\n\n{company_info_reply}"

        # 「会社情報」「社内情報」など明示キーワードが含まれるときのみ実行
        if any(kw in user_message for kw in ["会社情報", "社内情報", "情報検索"]):
            company_info_reply = search_company_info_by_keywords(user_message, user_name, user_data)
            if company_info_reply:
                reply_text += f"\n\n{company_info_reply}"

        rejection_phrases = ["申し訳", "できません", "わかりません", "お答えできません", "個人情報", "開示できません"]
        if any(phrase in reply_text for phrase in rejection_phrases):
            fallback = search_employee_info_by_keywords(user_message)
            if "📌" in fallback:  # 社内情報が見つかった場合のみ
                reply_text += "\n\n" + fallback
        
        if show_greeting and not any(reply_text.startswith(g) for g in greeting_keywords + ai_greeting_phrases):
            reply_text = f"{greeting}{user_name}。" + reply_text
    except Exception as e:
        logging.error("OpenAI 応答失敗: %s", e)
        reply_text = "⚠️ 応答に失敗しました。政美さんにご連絡ください。"

    log_conversation(now_jst().isoformat(), user_id, user_name, "AI", reply_text)

    # LINEへ返信
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# Flask起動直前にこの行を追加
threading.Thread(target=daily_summary_scheduler, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
