# data_cache.py

import os
import sys
import time
import threading

from write_read_commands.read_employee_info import read_employee_info
from write_read_commands.read_partner_info import read_partner_info
from write_read_commands.read_company_info import read_company_info
from write_read_commands.read_conversation_log import read_conversation_log
from write_read_commands.read_experience_log import read_experience_log
from write_read_commands.read_task_info import read_task_info
from write_read_commands.read_attendance_log import read_attendance_log

# キャッシュデータ格納用
cache = {
    "employee_info": [],
    "partner_info": [],
    "company_info": [],
    "conversation_log": [],
    "aiko_experience_log": [],
    "task_info": [],
    "attendance_info": []
}

# 最終更新時刻などのメタ情報（例: 30分更新用）
cache_metadata = {
    "conversation_log_last_update": 0,
    "conversation_log_ttl": 1800  # 30分
}

# 読み込み関数（import する read_xx_info を使う）
from read_employee_info import read_employee_info
from read_partner_info import read_partner_info
from read_company_info import read_company_info
from read_conversation_log import read_conversation_log
from read_aiko_experience_log import read_aiko_experience_log
from read_task_info import read_task_info
from read_attendance_info import read_attendance_log

def preload_all_data():
    print("📦 キャッシュ読み込み中...")
    cache["employee_info"] = read_employee_info()
    cache["partner_info"] = read_partner_info()
    cache["company_info"] = read_company_info()
    cache["conversation_log"] = read_conversation_log()
    cache["aiko_experience_log"] = read_aiko_experience_log()
    cache["task_info"] = read_task_info()
    cache["attendance_info"] = read_attendance_log()
    cache_metadata["conversation_log_last_update"] = time.time()
    print("✅ キャッシュ読み込み完了")

# 会話ログだけは30分ごとに更新
def refresh_conversation_log_if_needed():
    now = time.time()
    if now - cache_metadata["conversation_log_last_update"] > cache_metadata["conversation_log_ttl"]:
        cache["conversation_log"] = read_conversation_log()
        cache_metadata["conversation_log_last_update"] = now
        print("🔁 会話ログキャッシュ更新完了")

# 起動時に一度だけキャッシュを事前読み込み
preload_all_data()
