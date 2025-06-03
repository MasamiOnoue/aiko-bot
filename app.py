import os
import traceback
import logging
import datetime
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

# ユーザーIDと名前のマッピング関数だけを定義
def load_user_id_map():
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2,
        range='従業員情報!A:W'
    ).execute().get("values", [])[1:]# 1列目のヘッダー除く
    return {row[2]: row[1] for row in result if len(row) >= 3}

# 環境変数読み込み
load_dotenv()

# ログ出力設定（INFO以上を表示）
logging.basicConfig(level=logging.INFO)

# Flask初期化
app = Flask(__name__)

# Google Sheets 設定
SERVICE_ACCOUNT_FILE = 'aiko-bot-log-cfbf23e039fd.json'
SPREADSHEET_ID1 = '14tFyTz_xYqHYwegGLU2g4Ez4kc37hBgSmR2G85DLMWE' #ログのスプレッドシート
_NAME1 = 'ログ!A:D'

SPREADSHEET_ID2 = '1kO7-r-D-iZzYzv9LEZ9J4FzVAaZ13WKJWT_-97F6vbM' #従業員情報のスプレッドシート
_NAME2 = '従業員情報!A:W'

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

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
        entry = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))
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
    def format_conversation_history(log, user_name, limit=200):
        recent = [row for row in log if len(row) >= 4 and row[1] == user_name][-limit:]
        return "\n".join([f"{row[1]}: {row[2]}\n愛子: {row[3]}" for row in recent])

    history = format_conversation_history(conversation_log, user_name)

    # 従業員情報取得
    employee_data_result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID2,
        range="従業員情報!A:W"
    ).execute().get("values", [])

    employee_info_text = format_employee_data_for_prompt(employee_data_result)

    # OpenAIに送信
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": f"""
                    あなたは社内で使われるAI秘書『愛子』です。以下は従業員の情報です。会話に必要な情報があればこれを参照して答えてください。個人情報は求められたときのみ返してください。
                    {employee_info_text}
                    また、最近のやりとりを以下に示します。
                    {history}
                    回答は簡潔に30文字以内で返してください。
                """
            },
            {"role": "user", "content": user_message}
        ]
    )
    reply_text = response.choices[0].message.content.strip()

    # 🔽 USER_IDを名前に変換（登録された人のみ）
    user_name = USER_ID_MAP.get(user_id, f"未登録 ({user_id})")  # 見つからなければIDを残す

    # 🔽 会話ログを Google Sheets に保存
    timestamp = datetime.datetime.now().isoformat()
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID1,
        range=RANGE_NAME1,
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
