# aiko_diary_report.py

from datetime import datetime, timedelta
import pytz
import openai
import os
from company_info import get_conversation_log, write_company_info

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

    # OpenAIに渡すプロンプトを作成
    text = "\n".join([f"{log['発言者']}: {log['メッセージ内容']}" for log in recent_logs])
    prompt = f"以下は愛子とユーザーの会話ログです。これらをもとに今日の業務や出来事を1000文字以内で要約してください。\n\n{text}"

    # OpenAIへ問い合わせ
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたはAIアシスタント愛子です。"},
                {"role": "user", "content": prompt}
            ]
        )
        summary = response.choices[0].message.content.strip()
        date_str = now.strftime("%Y-%m-%d")
        write_company_info(date_str, summary)
        return summary
    except Exception as e:
        return f"要約の作成に失敗しました: {e}"
