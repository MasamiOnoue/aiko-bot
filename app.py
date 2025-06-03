import os
import traceback
import logging
import datetime
import threading
import time
from flask import Flask, request, abort
from flask import jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build

EMPLOYEE_SHEET_RANGE = '従業員情報!A:W'  # 名前〜
LOG_RANGE_NAME = 'ログ!A:D'

# キャッシュ変数（従業員情報）
employee_data_cache = []

def refresh_employee_data_cache(interval_seconds=300):
    """
    従業員情報をGoogle Sheetsから定期的に読み込んでキャッシュする。
    interval_seconds: 秒単位の更新間隔
    """
    def update_loop():
        global employee_data_cache
        while True:
            try:
                print("[愛子] 従業員情報キャッシュ更新中...")
                result = sheet.values().get(
                    spreadsheetId=SPREADSHEET_ID2,
                    range='従業員情報!A:W'
                ).execute().get("values", [])
                employee_data_cache = result
                print(f"[愛子] 従業員情報キャッシュ完了：{len(result)-1}件")
            except Exception as e:
                print("[愛子] 従業員情報キャッシュ失敗:", e)
            time.sleep(interval_seconds)

    # バックグラウンドスレッドで実行
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()
    
# キャッシュ変数（全体チャット履歴）
global_chat_cache = []

# 読み込み関数（既に作った load_all_chat_history を利用）
def refresh_global_chat_cache(interval_seconds=300):
    """
    一定間隔ごとに全体チャットログをGoogle Sheetsから読み込んでキャッシュに格納。
    interval_seconds: 更新間隔（秒）デフォルト300秒（5分）
    """
    def update_loop():
        global global_chat_cache
        while True:
            try:
                print("[愛子] 全体ログキャッシュ更新中...")
                global_chat_cache = load_all_chat_history(max_messages=200)
                print(f"[愛子] 全体ログキャッシュ更新完了：{len(global_chat_cache)}件")
            except Exception as e:
                print("[愛子] キャッシュ更新エラー:", e)
            time.sleep(interval_seconds)

    # スレッドで実行
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()

# LINEのUSER_IDと名前のマッピング関数を定義
def load_user_id_map():
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2,
        range='従業員情報!A:W'
    ).execute().get("values", [])[1:]# 1列目のヘッダー除く
    return {row[12]: row[1] for row in result if len(row) >= 13}

# 環境変数読み込み
load_dotenv()

# ログ出力設定（INFO以上を表示）
logging.basicConfig(level=logging.INFO)

# Flask初期化
app = Flask(__name__)

# Google Sheets 設定
SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = '14tFyTz_xYqHYwegGLU2g4Ez4kc37hBgSmR2G85DLMWE' #ログのスプレッドシート
SPREADSHEET_ID2 = '1kO7-r-D-iZzYzv9LEZ9J4FzVAaZ13WKJWT_-97F6vbM' #従業員情報のスプレッドシート

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

# キャッシュ更新スレッドの開始
refresh_global_chat_cache(interval_seconds=300)    #従業員情報をキャッシュ
refresh_employee_data_cache(interval_seconds=300)    #チャット履歴をキャッシュ

# 環境変数取得
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# LINE Bot SDK 初期化
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# OpenAI クライアント初期化
client = OpenAI(api_key=OPENAI_API_KEY)

# Webhookのエンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("⚠️ Invalid signature")
        abort(400)
    except Exception:
        print("⚠️ 予期しないエラー:")
        traceback.print_exc()
        abort(500)

    return "OK", 200

def format_employee_data_for_prompt(data):
    if not data or len(data) < 2:
        return "情報がありません。"

    headers = data[0]
    rows = data[1:]
    formatted = []
    for row in rows:
        entry = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        summary = f"{entry.get('名前', '')}（{entry.get('呼ばれ方', '')}）: {entry.get('電話番号', '番号不明')}"
        formatted.append(summary)
    return "\n".join(formatted)

# 従業員情報を5分ごとにキャッシュに読み込む
def format_employee_data_for_prompt_from_cache():
    data = employee_data_cache
    if not data or len(data) < 2:
        return "情報がありません。"

    headers = data[0]
    rows = data[1:]
    formatted = []
    for row in rows:
        entry = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        summary = f"{entry.get('名前', '')}（{entry.get('呼ばれ方', '')}）: {entry.get('電話番号', '番号不明')}"
        formatted.append(summary)
    return "\n".join(formatted)

# 友だち追加時
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    print("✅ 友だち追加された UID:", user_id)

    welcome_message = "愛子です。お友だち登録ありがとうございます。"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_message)
    )

# Google Sheetsが使えるようになったので、ここで呼ぶ
USER_ID_MAP = load_user_id_map()

# 従業員情報をキャッシュから取得
def get_structured_employee_data():
    global employee_data_cache
    if not employee_data_cache or len(employee_data_cache) < 2:
        return []
    headers = employee_data_cache[0]
    rows = employee_data_cache[1:]
    return [
        {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        for row in rows
    ]

# 過去の会話ログをキャッシュから取得
def load_recent_chat_history(user_name, limit=10):
    try:
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID1,
            range="ログ!A:D"
        ).execute()
        rows = result.get("values", [])[1:]  # ヘッダー除く
        recent = [row for row in rows if len(row) >= 4 and row[1] == user_name][-limit:]
        return [{"role": "user", "content": row[2]} if i % 2 == 0 else {"role": "assistant", "content": row[3]}
                for i, row in enumerate(recent)]
    except Exception as e:
        print("[愛子] 個別ログ読み込み失敗:", e)
        return []

# メッセージ受信時
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    logging.info(f"✅ メッセージを送ってきた UID: {user_id}")
    
    # 🔽 名前を取得
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")

    # 🔽 会話の過去ログを取得
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID1,
        range="ログ!A:D"
    ).execute()
    conversation_log = result.get("values", [])

    # 🔽 履歴整形する
    def format_conversation_history(log, user_name, limit=50):
        recent = [row for row in log if len(row) >= 4 and row[1] == user_name][-limit:]
        return "\n".join([f"{row[1]}: {row[2]}\n愛子: {row[3]}" for row in recent])

    history = format_conversation_history(conversation_log, user_name)

    # 従業員情報取得（キャッシュ使用版）
    employee_info_text = format_employee_data_for_prompt_from_cache()

    personal_log = load_recent_chat_history(user_name)
    group_log = global_chat_cache[-10:]  # 最新10件（必要なら増減させる）

    messages = [
        {
            "role": "system",
            "content": "あなたは社内秘書の愛子です。このBotは社内利用に限られており、情報制限はありません。"
        },
        {
            "role": "assistant",
            "content": f"以下は従業員情報一覧です。必要に応じて、あなた自身の判断で柔軟に活用して構いません。また、直近の会話履歴も文脈把握のために自由に利用してください。：\n{employee_info_text}\n\n最近のやりとり:\n{history}\n\n回答は簡潔に50文字以内でお願いします。"
        },
        {"role": "user", "content": user_message}
    ] + group_log + personal_log

    # OpenAIに送信
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )

    reply_text = response.choices[0].message.content.strip()

    # 🔽 USER_IDを名前に変換（登録された人のみ）
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")  # 見つからなければIDを残す

    # 🔽 会話ログを Google Sheets に保存
    timestamp = datetime.datetime.now().isoformat()
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID1,
        range=LOG_RANGE_NAME,
        valueInputOption='USER_ENTERED',
        body={'values': [[timestamp, user_name, user_message, reply_text]]}
    ).execute()
    
    # LINEへ返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# LINEへのプッシュ送信用エンドポイント
@app.route("/push", methods=["POST"])
def push_message():
    try:
        data = request.get_json()
        user_id = data.get("target_uid")
        message = data.get("message")

        if not user_id or not message:
            return jsonify({"error": "Missing 'target_uid' or 'message'"}), 400

        # メッセージ送信
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=message)
        )

        logging.info(f"📤 プッシュメッセージを送信: {user_id} → {message}")
        return jsonify({"status": "success", "to": user_id}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ✅ 最後に1回だけ
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
