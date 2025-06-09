import logging

# === 会話ログ書き込み関数 ===
def write_conversation_log(sheet_values, timestamp, user_id, user_name, speaker, message, category):
    try:
        row = [timestamp, user_id, user_name, speaker, message, category, "text", "", "OK", ""]
        body = {"values": [row]}
        sheet_values.append(
            spreadsheetId=os.getenv("SPREADSHEET_ID1"),
            range="会話ログ!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        logging.error(f"❌ 会話ログ書き込みエラー: {e}")
