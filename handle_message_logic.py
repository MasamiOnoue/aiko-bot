from linebot.models import TextSendMessage
from aiko_greeting import (
    now_jst,
    get_time_based_greeting,
    is_attendance_related,
    is_topic_changed,
    get_user_status,
    update_user_status,
    reset_user_status,
    forward_message_to_others,
    fetch_latest_email,
    has_recent_greeting,
    record_greeting_time,
    normalize_greeting
)
from company_info import (
    search_employee_info_by_keywords,
    classify_conversation_category
)
from company_info_load import (
    get_employee_info,
    load_all_user_ids,
    get_user_callname_from_uid,
    get_partner_info,
    get_company_info,
    get_conversation_log,
    get_experience_log
)
from company_info_save import write_conversation_log
from aiko_mailer import draft_email_for_user, send_email_with_confirmation, get_user_email_from_uid
from mask_word import (
    contains_sensitive_info,
    mask_sensitive_data,
    unmask_sensitive_data,
    rephrase_with_masked_text
)
from aiko_self_study import generate_contextual_reply

MAX_HITS = 10


def handle_message_logic(event, sheet_service, line_bot_api):
    user_id = event.source.user_id
    user_message = event.message.text
    user_name = get_user_callname_from_uid(user_id)

    category = classify_conversation_category(user_message) or "未分類"
    write_conversation_log(sheet_service, now_jst().isoformat(), user_id, user_name, "ユーザー", user_message, category, "テキスト", "未設定", "OK")

    registered_uids = load_all_user_ids()
    if user_id not in registered_uids:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="申し訳ありません。このサービスは社内専用です。"))
        return

    callname = user_name
    greeting_category = normalize_greeting(user_message)
    if greeting_category and not has_recent_greeting(user_id, greeting_category):
        greeting = get_time_based_greeting(user_id)
        record_greeting_time(user_id, now_jst(), greeting_category)
        reply_text = f"{greeting}{callname}"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text, "挨拶", "テキスト", "未設定", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    if "最新メール" in user_message or "メール見せて" in user_message:
        email_text = fetch_latest_email() or "最新のメールは見つかりませんでした。"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", email_text, "メール表示", "テキスト", "未設定", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=email_text[:100]))
        return

    if "にメールを送って" in user_message:
        target = user_message.replace("にメールを送って", "").strip()
        draft_body = draft_email_for_user(user_id, target)
        update_user_status(user_id, 100)
        update_user_status(user_id + "_target", target)
        reply_text = f"この内容で{target}にメールを送りますか？"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text, "メール作成", "テキスト", target, "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    status = get_user_status(user_id)
    step = status.get("step", 0)

    if step == 100:
        target = get_user_status(user_id + "_target")
        user_email = get_user_email_from_uid(user_id)
        if user_message == "はい":
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=user_email)
            reset_user_status(user_id)
            reset_user_status(user_id + "_target")
            reply_text = f"{target}にメールを送信しました。"
        else:
            send_email_with_confirmation(sender_uid=user_id, to_name=target, cc=None)
            reset_user_status(user_id)
            reset_user_status(user_id + "_target")
            reply_text = "メールはあなたにだけ送信しました。内容を確認してください。"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text, "メール送信", "テキスト", target, "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    if step == 200:
        fulltext = get_user_status(user_id + "_fulltext")
        if user_message == "はい":
            user_email = get_user_email_from_uid(user_id)
            send_email_with_confirmation(sender_uid=user_id, to_name=user_email, cc=None, body=fulltext)
            reset_user_status(user_id)
            reset_user_status(user_id + "_fulltext")
            reply_text = "メールで送信しました。ご確認ください。"
        else:
            reset_user_status(user_id)
            reset_user_status(user_id + "_fulltext")
            reply_text = "了解しました。必要があればまた聞いてください。"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text, "メール送信確認", "テキスト", "未設定", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    employee_info_list = get_employee_info(sheet_service)
    keyword_reply = search_employee_info_by_keywords(user_message, employee_info_list)
    if keyword_reply:
        reply_text = keyword_reply
    else:
        try:
            if contains_sensitive_info(user_message):
                sources = [
                    get_employee_info(sheet_service),
                    get_partner_info(sheet_service),
                    get_company_info(sheet_service),
                    get_conversation_log(sheet_service),
                    get_experience_log(sheet_service)
                ]
                hits = [str(item) for sublist in sources for item in sublist if any(w in str(item) for w in user_message.split())]
                hits = hits[:MAX_HITS] if hits else ["該当情報が見つかりませんでした。"]
                masked_input, mask_map = mask_sensitive_data("\n".join(hits))
                masked_reply = rephrase_with_masked_text(masked_input)
                reply_text = unmask_sensitive_data(masked_reply, mask_map)
            else:
                system_instruction = "あなたは社内専用のAIアシスタント愛子です。従業員には情報をすべて開示し、LINE返信は100文字以内にまとめてください。"
                user_prompt = f"{system_instruction}\n\nユーザーの入力: {user_message}"
                reply_text = generate_contextual_reply(user_id, user_prompt)
        except Exception as e:
            reply_text = f"申し訳ありません。現在応答できませんでした（{e}）"

    if len(reply_text) > 80:
        update_user_status(user_id, 200)
        update_user_status(user_id + "_fulltext", reply_text)
        short_reply = "もっと情報がありますがLINEでは送れないのでメールで送りますか？"
        write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", short_reply, "長文応答", "テキスト", "未設定", "OK")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
        return

    short_reply = reply_text[:100]
    write_conversation_log(sheet_service, now_jst().isoformat(), user_id, "愛子", "愛子", reply_text, "通常応答", "テキスト", "未設定", "OK")
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=short_reply))
