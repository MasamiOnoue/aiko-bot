#   information_reader_from_cache.py

from data_cache import cache, refresh_conversation_log_if_needed

def get_employee_info():
    return cache["employee_info"]

def get_partner_info():
    return cache["partner_info"]

def get_company_info():
    return cache["company_info"]

def get_conversation_log_from_cache():
    refresh_conversation_log_if_needed()
    """
    Cloud Run 経由で会話ログを取得し、キャッシュとして保持する。
    初回読み込み時のみAPIを叩く。
    """
    global full_conversation_cache
    if full_conversation_cache:
        return full_conversation_cache

    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-conversation-log"
        api_key = os.getenv("PRIVATE_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        records = result.get("records", [])

        full_conversation_cache = records
        return records

    except Exception as e:
        logging.error(f"❗Cloud Run経由の会話ログ取得に失敗しました: {e}")
        return []

    return cache["conversation_log"]

def get_aiko_experience_log():
    return cache["aiko_experience_log"]

def get_task_info():
    return cache["task_info"]

def get_attendance_info():
    return cache["attendance_info"]
