import os
import traceback
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from dotenv import load_dotenv
from openai import OpenAI

# 環境変数読み込み
load_dotenv()

# Flask初期化
app = Flask(__name__)

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

# メッセージ受信時
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    print("✅ メッセージを送ってきた UID:", user_id)

    user_message = event.message.text

    # OpenAI APIに送信
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "あなたは親しみやすく頼れるAI秘書『愛子』です。LINEでは簡潔に、30文字以内で答えてください。"},
            {"role": "user", "content": user_message}
        ]
    )

    reply_text = response.choices[0].message.content.strip()

    # LINEへ返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# ポート指定（Render対応）
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
