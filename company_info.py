# company_info.py に分離すべき会社・従業員情報・会話ログ・取引先情報・経験ログ処理
import os
import logging
from datetime import datetime
import pytz
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import openai
import json

openai.api_key = os.getenv("OPENAI_API_KEY")

# ✅ SPREADSHEET_ID の読み込み確認
SPREADSHEET_ID1 = os.getenv('SPREADSHEET_ID1')  # 会話ログ
SPREADSHEET_ID2 = os.getenv('SPREADSHEET_ID2')  # 従業員情報
SPREADSHEET_ID3 = os.getenv('SPREADSHEET_ID3')  # 取引先情報
SPREADSHEET_ID4 = os.getenv('SPREADSHEET_ID4')  # 会社情報
SPREADSHEET_ID5 = os.getenv('SPREADSHEET_ID5')  # 愛子の経験ログ

for sid, label in [
    (SPREADSHEET_ID1, "SPREADSHEET_ID1"),
    (SPREADSHEET_ID2, "SPREADSHEET_ID2"),
    (SPREADSHEET_ID3, "SPREADSHEET_ID3"),
    (SPREADSHEET_ID4, "SPREADSHEET_ID4"),
    (SPREADSHEET_ID5, "SPREADSHEET_ID5"),
]:
    if not sid:
        logging.error(f"❌ {label} が定義されていません")
    else:
        logging.info(f"✅ {label} = {sid}")
        
#グローバル変数としてキャッシュを定義
employee_info_cache = None

# ==== Googleのシート共有サービスを宣言（ローカルのJSONファイルから読み込み方式） ====
def get_google_sheets_service():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'aiko-bot-log-cfbf23e039fd.json')
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=credentials)
        return service.spreadsheets()
    except Exception as e:
        logging.error(f"❌ Google Sheets Serviceの初期化に失敗: {e}")
        return None

# ==== .gitignore に追加すべき項目 ====
# aiko-bot-log-584180f0987f.json（GitHubには含めない）

# ==== 会社情報スプレッドシートの列構成定義 ====
COMPANY_INFO_COLUMNS = {
    "カテゴリ": 0,
    "キーワード": 1,
    "質問例": 2,
    "回答内容": 3,
    "回答要約": 4,
    "補足情報": 5,
    "最終更新日": 6,
    "登録者名": 7,
    "使用回数": 8,
    "担当者": 9,
    "開示範囲": 10,
    "予備2": 11,
    "予備3": 12,
    "予備4": 13,
    "予備5": 14,
    "予備6": 15,
    "予備7": 16,
    "予備8": 17,
    "予備9": 18,
    "予備10": 19,
    "予備11": 20,
    "予備12": 21,
    "予備13": 22,
    "予備14": 23,
    "予備15": 24,
    "予備16": 25
}

# ---------------- 判定系 関数 ----------------
# 会話ログのF列（カテゴリー）をOpenAIに判定させる
def classify_message_context(message):
    prompt = f"""次の発言を、以下の分類から最も近いもの1つを日本語で選んでください：
- 業務連絡
- あいさつ
- 日常会話
- ネットからの情報
- 愛子botから社内情報報告
- 重要
- エラー

発言:
「{message}」

分類:"""
    try:
        response = openai.ChatCompletion.create(  # ← 修正済み
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=30
        )
        result = response.choices[0].message["content"].strip()

        if result not in ["業務連絡", "あいさつ", "日常会話", "ネットからの情報", "愛子botから社内情報報告", "重要", "エラー"]:
            logging.warning(f"分類結果が不正: {result}")
            return "未分類"
        return result
    except Exception as e:
        logging.warning(f"OpenAI分類失敗: {e}")
        return "未分類"

# ---------------- 読み込み系 関数 ----------------

# 会話ログを取得（SPREADSHEET_ID1）
def get_conversation_log(sheet, spreadsheet_id=SPREADSHEET_ID1):
    try:
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range="会話ログ!A2:D"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"会話ログの取得に失敗: {e}")
        return []

# 従業員情報を取得（SPREADSHEET_ID2）
def get_employee_info(sheet_service, spreadsheet_id=SPREADSHEET_ID2, retries=3, delay=2):
    try:
        for attempt in range(retries):
            try:
                result = sheet_service.values().get(
                    spreadsheetId=spreadsheet_id,
                    range="従業員情報!A2:W"
                ).execute()
                values = result.get("values", [])
                keys = [
                    "名前", "名前の読み", "呼ばれ方", "愛子ちゃんからの呼ばれ方", "役職", "入社年",
                    "生年月日", "メールアドレス", "LINE名", "社員コード", "部署", "在籍状況",
                    "備考", "UID", "登録日時", "更新日時", "退職日", "タグ", "よく話す内容",
                    "最終ログイン", "LINE登録日", "Slack名"
                ]
                employee_info_map = {}
                for row in values:
                    row_data = {keys[i]: row[i] if i < len(row) else "" for i in range(len(keys))}
                    uid = row_data.get("UID") or row_data.get("社員コード") or row_data.get("名前")
                    if uid:
                        employee_info_map[uid] = row_data
                return employee_info_map
            except HttpError as e:
                logging.warning(f"⚠️ 従業員情報の取得失敗（{attempt+1}回目）: {e}")
                time.sleep(delay)
        return {}
    except Exception as e:
        logging.error(f"❌ 予期しないエラー: {e}")
        return {}

# キーワードから従業員情報を検索
def search_employee_info_by_keywords(query, employee_info_map):
    attribute_keywords = {
        "名前": ["名前", "氏名"],
        "名前の読み": ["名前の読み", "読み", "よみ"],
        "役職": ["役職", "肩書", "ポスト", "仕事", "役割"],
        "入社年": ["入社年", "入社", "最初の年"],
        "生年月日": ["生年月日", "生まれ", "誕生日", "バースデー"],
        "メールアドレス": ["メールアドレス", "メール", "e-mail", "連絡", "アドレス", "メアド"],
        "携帯電話番号": ["携帯電話番号", "携帯", "携帯番号", "携帯電話", "電話番号", "携帯は", "携帯番号は", "携帯電話番号は", "連絡先"],
        "自宅電話": ["自宅電話", "電話", "番号", "電話番号", "自宅の電"],
        "住所": ["住所", "所在地", "場所", "どこ"],
        "郵便番号": ["郵便番号", "〒", "郵便"],
        "緊急連絡先": ["緊急連絡先", "緊急", "問い合わせ先", "至急連絡"],
        "ペット情報": ["ペット情報", "犬", "猫", "いぬ", "イヌ", "ネコ", "ねこ", "にゃんこ", "わんちゃん", "わんこ"],
        "性格": ["性格", "大人しい", "うるさい", "性質", "特性"],
        "口癖": ["口癖", "よく言う", "よく語る", "軟着陸"],
        "備考": ["備考", "その他"],
        "追加情報": ["追加情報", "部署", "部門", "部"],
        "家族": ["家族", "配偶者", "妻", "夫", "子供", "扶養", "ペット", "犬", "猫", "いぬ", "ねこ", "わんちゃん"]
    }

    result_texts = []
    lowered_query = query.lower()
    for uid, data in employee_info_map.items():
        for attr, keywords in attribute_keywords.items():
            for keyword in keywords:
                if keyword.lower() in lowered_query:
                    value = data.get(attr) or data.get(attr.replace("携帯電話番号", "携帯番号"))
                    if not value:
                        continue
                    if attr not in data:
                        continue
                    result_texts.append(f"📌 {data.get('名前', '不明')}の{attr}は「{value}」です。")
    if result_texts:
        return "\n".join(result_texts)

    keywords = query.split()
    for data in employee_info_map.values():
        if any(k in str(data.values()) for k in keywords):
            return "🔎 社内情報から見つけました: " + ", ".join(f"{k}: {v}" for k, v in data.items())

    return "⚠️ 社内情報でも見つかりませんでした。"


# 取引先情報を取得（SPREADSHEET_ID3）
def get_partner_info(sheet, spreadsheet_id=SPREADSHEET_ID3):
    try:
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range="取引先情報!A2:Z"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"取引先情報の取得に失敗: {e}")
        return []

# 会社情報を取得（SPREADSHEET_ID4）
def get_company_info(sheet, spreadsheet_id=SPREADSHEET_ID4):
    try:
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range="会社情報!A2:Z"
        ).execute()
        values = result.get("values", [])
        return {row[0]: row[1] for row in values if len(row) >= 2}
    except Exception as e:
        logging.error(f"会社情報の取得に失敗: {e}")
        return {}

# 経験ログを取得（SPREADSHEET_ID5）
def get_experience_log(sheet, spreadsheet_id=SPREADSHEET_ID5):
    try:
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range="経験ログ!A2:D"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        logging.error(f"経験ログの取得に失敗: {e}")
        return []

# ---------------- 保存系 関数 ----------------

# 会話ログを保存（SPREADSHEET_ID1）
def append_conversation_log(sheet, user_id, user_name, message, timestamp, spreadsheet_id=SPREADSHEET_ID1):
    try:
        row = [timestamp.strftime("%Y-%m-%d %H:%M:%S"), user_id, user_name, message]
        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range="会話ログ!A2:D",
            valueInputOption="USER_ENTERED",
            body={"values": [row]}
        ).execute()
    except Exception as e:
        logging.error(f"会話ログの保存に失敗: {e}")

# 会社情報を保存（SPREADSHEET_ID4）
def append_company_info(sheet, key, value, spreadsheet_id=SPREADSHEET_ID4):
    try:
        row = [key, value]
        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range="会社情報!A2:Z",
            valueInputOption="USER_ENTERED",
            body={"values": [row]}
        ).execute()
    except Exception as e:
        logging.error(f"会社情報の保存に失敗: {e}")

# 経験ログを保存（SPREADSHEET_ID5）
def append_experience_log(sheet, row, spreadsheet_id=SPREADSHEET_ID5):
    try:
        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range="経験ログ!A2:D",
            valueInputOption="USER_ENTERED",
            body={"values": [row]}
        ).execute()
    except Exception as e:
        logging.error(f"経験ログの保存に失敗: {e}")

# 日報まとめ生成（毎日3時用）
def generate_daily_summaries(sheet, employee_info_map, spreadsheet_id=SPREADSHEET_ID1):
    try:
        jst = pytz.timezone("Asia/Tokyo")
        today = datetime.now(jst).strftime("%Y-%m-%d")
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range="会話ログ!A2:D"
        ).execute()
        values = result.get("values", [])
        summaries = {}
        for row in values:
            if len(row) < 4:
                continue
            timestamp, user_id, user_name, message = row
            if today in timestamp:
                if user_name not in summaries:
                    summaries[user_name] = []
                summaries[user_name].append(f"・{message}")
        return summaries
    except Exception as e:
        logging.error(f"日報生成に失敗: {e}")
        return {}

# 日報シートに書き込む（毎日3時用）
def write_daily_summary(sheet, summaries, spreadsheet_id=SPREADSHEET_ID1):
    try:
        jst = pytz.timezone("Asia/Tokyo")
        today = datetime.now(jst).strftime("%Y-%m-%d")
        rows = [[today, name, "\n".join(messages)] for name, messages in summaries.items()]
        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range="日報まとめ!A2:C",
            valueInputOption="USER_ENTERED",
            body={"values": rows}
        ).execute()
    except Exception as e:
        logging.error(f"日報書き込みに失敗: {e}")

# ---------------- 補助 関数 ----------------

# 名前や役職から従業員を検索
def find_employee_by_name_or_title(employee_info_map, keyword):
    results = []
    for uid, info in employee_info_map.items():
        if keyword in info.get("名前", "") or keyword in info.get("役職", ""):
            results.append((uid, info))
    return results

# UIDから名前を取得
def get_name_by_uid(employee_info_map, uid):
    return employee_info_map.get(uid, {}).get("名前", "")

# UIDからタグ一覧を取得
def get_employee_tags(employee_info_map, uid):
    return employee_info_map.get(uid, {}).get("タグ", "").split(",")

# ---------------- 愛子の気分別テンプレート ----------------

aiko_moods = {
    "normal": [
        "了解しました。",
        "承知しました。",
        "わかりました、対応します。",
    ],
    "tsundere": [
        "べ、別にあんたのために答えるんじゃないんだからねっ…！",
        "ふん、これくらい朝飯前よ…！感謝なんていらないんだからっ",
        "あんたが困ってるから、しょうがなく助けてあげるだけよっ！",
    ],
    "cheerful": [
        "やったー！一緒にがんばりましょ♪",
        "わーい、なんでも聞いてくださいねっ！",
        "えへへ、私って頼りになるでしょ？",
    ],
    "cool": [
        "……完了。必要があれば次を指示して。",
        "以上、処理は済んだわ。余計なことは聞かないで。",
        "静かに。私はAI、感情に左右されないの。",
    ],
}
