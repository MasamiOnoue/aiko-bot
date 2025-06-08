# aiko_diary_report.py

from datetime import datetime, timedelta
import pytz
import openai
import os
import random
from company_info import get_conversation_log, write_company_info
from linebot import LineBotApi
from linebot.models import TextSendMessage

# JST取得関数
def now_jst():
    return datetime.now(pytz.timezone("Asia/Tokyo"))

# JST時刻を文字列からパース
def parse_jst(timestamp_str):
    try:
        naive_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
        return pytz.timezone("Asia/Tokyo").localize(naive_dt)
    except Exception:
        return now_jst()  # フォーマットが異なる場合は現在時刻で代用

# 愛子の日報を作成する関数
def generate_daily_report():
    now = now_jst()
    one_day_ago = now - timedelta(hours=24)

    # 会話ログを取得
    logs = get_conversation_log()
    recent_logs = [log for log in logs if 'タイムスタンプ' in log and parse_jst(log['タイムスタンプ']) > one_day_ago]

    if not recent_logs:
        return "この24時間で記録された会話が見つかりませんでした。"

    # OpenAIに渡すプロンプトを作成
    text = "\n".join([f"{log['発言者']}: {log['メッセージ内容']}" for log in recent_logs])
    prompt = (
        "以下は愛子とユーザーの会話ログです。"
        "これらをもとに『この24時間でどんな仕事をしたのか』を2000文字以内でまとめてください。"
        "文体は愛子らしく、口調は柔らかく、わかりやすくしてください。\n\n"
        f"{text}"
    )

    # ツンデレ愛子の気分別メッセージリスト
    closing_messages = [
        "……今日もよくがんばったのっ！（ドヤァ）",
        "ふん、別にサンネームのためにまとめたんじゃないんだからねっ！",
        "ちょっとだけ、やりきった気がするかも…なんてね♪",
        "これで明日もきっと大丈夫…だと思う、た、たぶんね",
        "やるじゃない、愛子。ちょっとだけ自分を褒めてあげたい",
        "工場で見たあの人、ちょっと今日はかっこよかったな",
        "今日は疲れたもうくったくたやねん",
        "明日もがんばるもん",
        "ちょーねむい、もう嫌！",
        "あーんもう嫌！誰かに癒されたい！",
        "今日もやりきったでござる"
    ]
    ending = random.choice(closing_messages)

    # OpenAIへ問い合わせ
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたはAIアシスタント愛子です。"},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content.strip()
        date_str = now.strftime("%Y-%m-%d")
        summary_with_ending = f"{summary}\n\n{ending}"
        write_company_info(date_str, summary_with_ending)
        return summary_with_ending
    except Exception as e:
        return f"要約の作成に失敗しました: {e}"

# LINEで日報を送信する処理（任意のタイミングで呼び出す）
def send_daily_report(line_bot_api: LineBotApi, user_id: str):
    summary = generate_daily_report()
    message = f"📋 愛子の日報です：\n\n{summary}"
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    except Exception as e:
        print(f"LINE送信エラー: {e}")
