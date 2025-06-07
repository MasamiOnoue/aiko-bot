import logging
from datetime import datetime
import pytz

# 日報まとめ生成（毎日3時用）
def generate_daily_summaries(sheet, employee_info_map, spreadsheet_id):
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
def write_daily_summary(sheet, summaries, spreadsheet_id):
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

# ==== 6時間ごとにブログの更新をチェック（ブログのタイトルが更新されていたら）してサマリーを記録する ====
def check_blog_updates():
    try:
        feed_url = "https://sun-name.com/bloglist/feed"  # RSSフィードURL
        feed = feedparser.parse(feed_url)
        existing_titles = get_read_titles_from_sheet()
        new_entries = []

        for entry in feed.entries:
            if entry.title not in existing_titles:
                new_entries.append(entry)
                register_blog_to_sheet(entry)

        if new_entries:
            logging.info(f"新しいブログ記事 {len(new_entries)} 件を会社情報に登録しました")
        else:
            logging.info("新しいブログ記事はありません")

    except Exception as e:
        logging.error(f"ブログチェック失敗: {e}")


