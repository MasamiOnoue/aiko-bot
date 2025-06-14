# attendance_logger.py

from datetime import datetime
import pytz

def log_attendance_from_qr(user_id, qr_text, spreadsheet_id, attendance_type):
    from sheet_service import get_google_sheets_service  # 適宜調整
    from company_info import get_user_callname_from_uid
    from information_writer import write_conversation_log

    service = get_google_sheets_service()
    sheet = service.spreadsheets()
    sheet_name = "勤怠管理"

    # 現在の日付と時刻（JST）
    now = datetime.now(pytz.timezone("Asia/Tokyo"))
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # シート全体読み取り
    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1:N"
    ).execute()
    values = result.get("values", [])

    if not values:
        return "勤怠データが取得できませんでした。"

    headers = values[0]
    name_col = headers.index("名前")
    date_col = headers.index("日付")

    # UID→氏名の変換（簡易）
    user_name = get_user_callname_from_uid(user_id)
    if not user_name:
        return "ユーザー名が見つかりませんでした。"

    # 今日の自分の行を探す
    row_index = None
    existing_row = None
    for i, row in enumerate(values[1:], start=2):
        if len(row) > max(name_col, date_col) and row[date_col] == today_str and row[name_col] == user_name:
            row_index = i
            existing_row = row
            break

    log_message = ""

    # なければ新しい行を作成
    if row_index is None:
        row_data = [""] * len(headers)
        row_data[date_col] = today_str
        row_data[name_col] = user_name
        if attendance_type == "出勤":
            row_data[headers.index("出勤時刻")] = time_str
        elif attendance_type == "退勤":
            row_data[headers.index("退勤時刻")] = time_str

        sheet.values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [row_data]}
        ).execute()

        log_message = f"{attendance_type}時刻を新規記録しました：{time_str}"

    else:
        # 既存行を更新（冪等性の考慮）
        col_index = headers.index("出勤時刻") if attendance_type == "出勤" else headers.index("退勤時刻")
        current_value = existing_row[col_index] if len(existing_row) > col_index else ""

        if current_value:
            log_message = f"すでに{attendance_type}時刻が記録されています：{current_value}"
        else:
            cell_range = f"{sheet_name}!{chr(65 + col_index)}{row_index}"
            sheet.values().update(
                spreadsheetId=spreadsheet_id,
                range=cell_range,
                valueInputOption="USER_ENTERED",
                body={"values": [[time_str]]}
            ).execute()
            log_message = f"{attendance_type}時刻を更新しました：{time_str}"

    # 会話ログ送信
    write_conversation_log(
        timestamp=now.isoformat(),
        user_id=user_id,
        user_name=user_name,
        speaker="ユーザー",
        message=f"QRコードで{attendance_type}打刻",
        category="勤怠",
        message_type="テキスト",
        topic="QR勤怠",
        status="完了"
    )

    return log_message
