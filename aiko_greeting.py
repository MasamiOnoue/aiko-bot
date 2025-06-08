# aiko_greeting.py

import logging
from datetime import datetime, timedelta, timezone

# JSTでの現在時刻を返す関数
def now_jst():
    return datetime.now(timezone(timedelta(hours=9)))

# 時間帯に応じた挨拶を返す関数
def get_time_based_greeting():
    current_time = now_jst()
    logging.info(f"現在のJST時刻: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    hour = current_time.hour
    if 5 <= hour < 10:
        return "おはようございます。今日も一日がんばりましょう！"
    elif 10 <= hour < 12:
        return "こんにちは。午前の部、おつかれさまです。"
    elif 12 <= hour < 14:
        return "お昼の時間ですね。しっかり休んでくださいね。"
    elif 14 <= hour < 18:
        return "こんにちは。午後も引き続きがんばっていきましょう！"
    elif 18 <= hour < 22:
        return "こんばんは。今日もおつかれさまでした。"
    else:
        return "夜遅くまでごくろうさまです。無理せず休んでくださいね。"
