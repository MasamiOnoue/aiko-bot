# company_info.py（最新版：全情報ソース検索＋失敗ログ＋正規化＋UID判定＋従業員属性応答＋ログ出力対応）

import os
import logging
from functools import lru_cache
import requests
import difflib
import unicodedata

# === 正規化ユーティリティ ===
def normalize_text(text):
    return unicodedata.normalize("NFKC", text).lower().strip()

# === 従業員情報検索 ===
def search_employee_info_by_keywords(user_message, employee_info_list):
    attributes = {
        "役職": "役職", "入社年": "入社年", "生年月日": "生年月日", "性別": "性別",
        "メールアドレス": "メールアドレス", "個人メールアドレス": "個人メールアドレス",
        "携帯電話番号": "携帯電話番号", "自宅電話": "自宅電話", "住所": "住所",
        "郵便番号": "郵便番号", "緊急連絡先": "緊急連絡先", "ペット情報": "ペット情報",
        "性格": "性格", "家族構成": "家族構成"
    }

    norm_user_message = normalize_text(user_message)

    for record in employee_info_list:
        if not isinstance(record, dict):
            continue

        name_candidates = set()
        for key in ["氏名", "呼ばれ方", "愛子からの呼ばれ方", "愛子からの呼ばれ方２"]:
            val = record.get(key, "")
            if val:
                name_candidates.add(normalize_text(val.replace("さん", "").replace("くん", "").replace("ちゃん", "")))

        full_name = record.get("氏名", "").strip()
        if full_name:
            short_name = normalize_text(full_name[:2])
            name_candidates.add(short_name)

        if any(name in norm_user_message for name in name_candidates):
            matched_name = record.get("氏名", "").strip()
            for keyword, field in attributes.items():
                if keyword in user_message:
                    value = record.get(field, "").strip() or "不明"
                    response = f"{matched_name}さんの{keyword}は {value} です。"
                    logging.info(f"✅ 社員情報応答: {response}")
                    return response
            fallback = f"{matched_name}さんに関する情報ですね。もう少し具体的に聞いてみてください。"
            logging.info(f"ℹ️ 社員名一致のみ応答: {fallback}")
            return fallback

    logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return None

# === 取引先情報検索 ===
def search_partner_info_by_keywords(user_message, partner_info_list):
    attributes = ["会社名", "電話番号", "住所", "メールアドレス", "担当者"]
    norm_user_message = normalize_text(user_message)

    for record in partner_info_list:
        if not isinstance(record, dict):
            continue

        company_name = record.get("会社名", "").strip()
        if not company_name:
            continue

        if normalize_text(company_name) in norm_user_message:
            for attr in attributes:
                if attr in user_message:
                    value = record.get(attr, "").strip() or "不明"
                    response = f"{company_name}の{attr}は {value} です。"
                    logging.info(f"✅ 取引先情報応答: {response}")
                    return response
            fallback = f"{company_name}に関する情報ですね。もう少し具体的に聞いてみてください。"
            logging.info(f"ℹ️ 取引先名一致のみ応答: {fallback}")
            return fallback

    logging.warning(f"❗該当する取引先または属性が見つかりませんでした: '{user_message}'")
    return None

# === ログ情報（会社/会話/経験）検索 ===
def search_log_by_similarity(user_message, log_entries):
    normalized_query = normalize_text(user_message)
    candidates = []
    for entry in log_entries:
        if not isinstance(entry, dict):
            continue
        text = entry.get("メッセージ内容", "")
        if not text:
            continue
        normalized_text = normalize_text(text)
        score = difflib.SequenceMatcher(None, normalized_query, normalized_text).ratio()
        if score > 0.4:
            candidates.append((score, text))

    if candidates:
        candidates.sort(reverse=True)
        best_score, best_text = candidates[0]
        logging.info(f"✅ ログ応答（スコア: {best_score:.2f}）: {best_text}")
        return f"以前の記録より：{best_text}"

    logging.info("ℹ️ ログに一致なし")
    return None

def search_company_info_log(user_message, company_info_log):
    return search_log_by_similarity(user_message, company_info_log)

def search_aiko_experience_log(user_message, aiko_experience_log):
    return search_log_by_similarity(user_message, aiko_experience_log)

def search_conversation_log(user_message, conversation_log):
    return search_log_by_similarity(user_message, conversation_log)

# === 全検索失敗ログ ===
def log_if_all_searches_failed(results_dict):
    if all(result is None for result in results_dict.values()):
        logging.warning("❌ 全検索失敗：どの情報ソースからも該当データが見つかりませんでした")

# === UID関連ユーティリティ ===
@lru_cache(maxsize=128)
def get_user_callname_from_uid(user_id):
    try:
        url = os.getenv("GCF_ENDPOINT", "").rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        if not url or not api_key:
            logging.error("❌ API情報未設定")
            return "エラー"

        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        for record in values:
            uid = record.get("LINE UID", "").strip().upper()
            if uid == user_id.strip().upper():
                return record.get("愛子からの呼ばれ方", "").strip() or record.get("氏名", "").strip()

        logging.warning(f"⚠️ UID未登録: {user_id}")
        return "不明な方"
    except Exception as e:
        logging.error(f"❌ 呼び名取得エラー: {e}")
        return "エラー"

def load_all_user_ids():
    try:
        url = os.getenv("GCF_ENDPOINT", "").rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        if not url or not api_key:
            logging.error("❌ API情報未設定")
            return []

        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        result = []
        for record in values:
            uid = record.get("LINE UID")
            if isinstance(uid, str):
                uid = uid.strip().upper()
                if uid.startswith("U"):
                    result.append(uid)

        logging.info(f"✅ 読み込んだUID一覧: {result}")
        return result
    except Exception as e:
        logging.error(f"❌ UID取得失敗: {e}")
        return []
