# aiko_diary_report.py 　AI愛子が日報を生成しLINEで送信

import os
import random
from datetime import datetime, timedelta
import pytz
from linebot import LineBotApi
from linebot.models import TextSendMessage
from company_info_load import get_conversation_log, get_google_sheets_service
from company_info_save import write_company_info
from openai_client import client  # OpenAIクライアント

# JSTを使用

def now_jst():
    return datetime.now(pytz.timezone("Asia/Tokyo"))

def parse_jst(timestamp_str):
    try:
        naive_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
        return pytz.timezone("Asia/Tokyo").localize(naive_dt)
    except Exception:
        return now_jst()

# === AI愛子の日報を生成 ===
def generate_daily_report():
    now = now_jst()
    one_day_ago = now - timedelta(hours=24)

    sheet = get_google_sheets_service()
    logs = get_conversation_log(sheet)
    recent_logs = [log for log in logs if len(log) >= 5 and parse_jst(log[0]) > one_day_ago]

    if not recent_logs:
        return "この24時間で記録された会話が見つかりませんでした。"

    text = "\n".join([f"{log[3]}: {log[4]}" for log in recent_logs])
    prompt = (
        "以下は愛子とユーザーの会話ログです\n"
        "これらをもとに『この24時間でどんな仕事をしたのか』を2000文字以内でまとめてください\n"
        "文体は愛子らしく、口調は柔らかく、わかりやすくしてください\n\n"
        f"{text}"
    )

    endings = [
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
    ending = random.choice(endings)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたはAIアシスタント愛子です。"},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content.strip()
        date_str = now.strftime("%Y-%m-%d")
        summary_with_ending = f"{summary}\n\n{ending}"
        write_company_info(sheet, [date_str, summary_with_ending])
        return summary_with_ending
    except Exception as e:
        return f"要約の作成に失敗しました: {e}"

# === LINEで日報を送信 ===
def send_daily_report(line_bot_api: LineBotApi, user_id: str):
    summary = generate_daily_report()
    message = f"📋 愛子の日報です：\n\n{summary}"
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    except Exception as e:
        print(f"LINE送信エラー: {e}")
