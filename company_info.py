# company_info.py
#（安定版：UID取得の不具合修正＋「-」除去の処理追加＋UID判定強化＋属性不明時の応答追加＋OpenAIループ対応＋「折戸」名認識強化＋呼ばれ方多段一致対応＋取引先対応＋会社情報参照）

import os
import logging
from functools import lru_cache
import requests

# === 従業員情報検索 ===
def search_employee_info_by_keywords(user_message, employee_info_list):
    attributes = {
        "役職": "役職", "入社年": "入社年", "生年月日": "生年月日", "性別": "性別",
        "メールアドレス": "メールアドレス", "個人メールアドレス": "個人メールアドレス",
        "携帯電話番号": "携帯電話番号", "自宅電話": "自宅電話", "住所": "住所",
        "郵便番号": "郵便番号", "緊急連絡先": "緊急連絡先", "ペット情報": "ペット情報",
        "性格": "性格", "家族構成": "家族構成"
    }

    user_message = user_message.replace("ちゃん", "さん").replace("君", "さん").replace("くん", "さん")

    for record in employee_info_list:
        if not isinstance(record, dict):
            continue

        possible_names = set()
        for key in ["氏名", "呼ばれ方", "愛子からの呼ばれ方", "愛子からの呼ばれ方２"]:
            value = record.get(key, "").strip()
            if value:
                possible_names.update({
                    value, value + "さん", value + "ちゃん", value + "君"
                })

        full_name = record.get("氏名", "").strip()
        if full_name:
            if " " in full_name:
                last_name = full_name.split()[0]
            elif len(full_name) >= 2:
                last_name = full_name[:2]
            else:
                last_name = full_name
            possible_names.update({
                last_name, last_name + "さん", last_name + "ちゃん", last_name + "君"
            })

        if any(name in user_message for name in possible_names):
            matched_name = record.get("氏名", "").strip()
            for keyword, field in attributes.items():
                if keyword in user_message:
                    value = record.get(field, "").strip() or "不明"
                    return f"{matched_name}さんの{keyword}は {value} です。"
            return f"{matched_name}さんに関する情報ですね。もう少し具体的に聞いてみてください。"

    logging.warning(f"❗該当する従業員または属性が見つかりませんでした: '{user_message}'")
    return None  # ← OpenAIへループさせるためNoneに変更

# === 取引先情報検索 ===
def search_partner_info_by_keywords(user_message, partner_info_list):
    attributes = ["会社名", "電話番号", "住所", "メールアドレス", "担当者"]

    for record in partner_info_list:
        if not isinstance(record, dict):
            continue

        company_name = record.get("会社名", "").strip()
        if not company_name:
            continue

        if company_name in user_message:
            for attr in attributes:
                if attr in user_message:
                    value = record.get(attr, "").strip() or "不明"
                    return f"{company_name}の{attr}は {value} です。"
            return f"{company_name}に関する情報ですね。もう少し具体的に聞いてみてください。"

    logging.warning(f"❗該当する取引先または属性が見つかりませんでした: '{user_message}'")
    return None

# === 会社情報ログから参照（梅原さん対応） ===
def search_company_info_log(user_message, company_info_log):
    for entry in company_info_log:
        if not isinstance(entry, dict):
            continue

        text = entry.get("メッセージ内容", "")
        if any(name in user_message for name in ["梅原", "梅原さん", "うめはらさん"]):
            if "梅原" in text:
                return f"以前の記録より：{text}"

    return None

def load_all_user_ids():
    logging.info(f"📡 現在の GCF_ENDPOINT: {os.getenv('GCF_ENDPOINT')}")
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        if not api_key:
            logging.error("❌ APIキーが設定されていません")
            return []

        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        logging.info(f"🔍 APIから取得したデータ件数: {len(values)} 件")
        logging.debug(f"📄 APIレスポンスデータ: {values}")

        if not isinstance(values, list):
            logging.error("❌ スプレッドシートレスポンスが配列ではありません")
            return []

        result = []
        for record in values:
            if not isinstance(record, dict):
                continue
            uid = record.get("LINE UID")
            if isinstance(uid, str):
                uid = uid.strip().upper()
                if uid and uid.startswith("U") and len(uid) >= 10:
                    result.append(uid)

        logging.info(f"✅ 読み込んだUID一覧: {result}")
        return result
    except requests.exceptions.Timeout:
        logging.error("⏱️ APIタイムアウトが発生しました")
        return []
    except Exception as e:
        logging.error(f"❌ UID読み込みエラー: {e}")
        return []

@lru_cache(maxsize=128)
def get_user_callname_from_uid(user_id):
    try:
        base_url = os.getenv("GCF_ENDPOINT")
        if not base_url:
            raise ValueError("GCF_ENDPOINT 環境変数が設定されていません")

        url = base_url.rstrip("/") + "/read-employee-info"
        api_key = os.getenv("PRIVATE_API_KEY")
        if not api_key:
            logging.error("❌ APIキーが設定されていません")
            return "エラー"

        headers = {"x-api-key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        values = response.json().get("data", [])

        logging.info(f"🔍 呼び名取得対象データ件数: {len(values)} 件")
        logging.debug(f"📄 呼び名取得対象データ: {values}")

        if not isinstance(values, list):
            logging.error("❌ スプレッドシートレスポンスが配列ではありません")
            return "エラー"

        for record in values:
            if not isinstance(record, dict):
                continue
            uid = record.get("LINE UID")
            if isinstance(uid, str) and uid.strip().upper() == user_id.strip().upper():
                callname = record.get("愛子からの呼ばれ方", "").strip()
                return callname if callname else record.get("氏名", "").strip()

        logging.warning(f"⚠️ 該当するUIDが見つかりません: {user_id}")
        return "不明な方"
    except requests.exceptions.Timeout:
        logging.error("⏱️ 呼び名取得のAPIタイムアウト")
        return "タイムアウト"
    except Exception as e:
        logging.error(f"❌ 呼び名取得エラー: {e}")
        return "エラー"
