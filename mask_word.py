# mask_word.py　OpenAIに個人情報や会社の機密情報を渡さずに処理をさせるためのマスクとマスク解除処理ルーチン

import re
import uuid
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 個人情報らしいワード（OpenAI経由禁止）
SENSITIVE_KEYWORDS = [
    "誕生日", "生年月日", "入社", "入社年", "住所", "電話", "家族", "名前", "氏名",
    "読み", "ふりがな", "携帯", "出身", "血液型", "メール", "メールアドレス",
    "年齢", "生まれ", "個人", "趣味", "特技", "身長", "体重"
]

# 個人情報が含まれるか判定
def contains_sensitive_info(text):
    pattern = "|".join(map(re.escape, SENSITIVE_KEYWORDS))
    return re.search(pattern, text, re.IGNORECASE) is not None

# テキストをダミーに置換（マスキング）
def mask_sensitive_data(text):
    mask_map = {}
    masked_text = text
    for word in set(re.findall('|'.join(SENSITIVE_KEYWORDS), text)):
        mask = f"[[MASK-{uuid.uuid4().hex[:6]}]]"
        mask_map[mask] = word
        masked_text = masked_text.replace(word, mask)
    return masked_text, mask_map

# ダミーを元の語に戻す（アンマスキング）
def unmask_sensitive_data(text, mask_map):
    for mask, original in mask_map.items():
        text = text.replace(mask, original)
    return text

# OpenAIで自然な日本語に整形（マスク付き）
def rephrase_with_masked_text(masked_input):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたはサンネームで自然な日本語に直すAIアシスタント愛子です。以下は社内情報の候補です。自然な日本語でまとめてください。ただし個人情報はマスク済みです。"},
                {"role": "user", "content": masked_input}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[マスク応答失敗]: {e}"
