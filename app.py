import os
import openai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

# 環境変数読み込み（ローカル開発用）
load_dotenv()

# Flaskアプリ初期化
app = Flask(__name__)

# 環境変数から各種キー取得
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 環境変数の読み込み確認（Renderのデバッグ用）
print("==DEBUG== Loading environment variables...")
print("LINE_CHANNEL_SECRET:", CHANNEL_SECRET)
print("LINE_CHANNEL_ACCESS_TOKEN:", CHANNEL_ACCESS_TOKEN)
print("OPENAI_API_KEY:", OPENAI_API_KEY)

# LINE・OpenAIのAPI初期化
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# LINEからのWebhookを受け取るエンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    print("=== Debug: signature ===")
    print(signature)
    print("=== Debug: body ===")
    print(body)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("⚠️ handler.handle() でエラー")
        import traceback
        traceback.print_exc()
        abort(500)

    return "OK"

# メッセージ受信時の処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    # 最新の openai ライブラリに対応した書き方（v1.0以降）
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "あなたは親しみやすく頼れるAI秘書『愛子ちゃん』です。生産性や業務改善をやさしく丁寧にサポートしてください。"},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
    )

    reply_text = response.choices[0].message.content.strip()

    # LINE に返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# Render対応：正しいhost/portで起動
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
