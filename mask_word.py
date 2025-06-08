# mask_word.py
import re
import openai

# 個人情報らしいワード（OpenAI経由禁止）
SENSITIVE_KEYWORDS = [
    "誕生日", "生年月日", "入社", "入社年", "住所", "電話", "家族", "名前", "氏名",
    "読み", "ふりがな", "携帯", "出身", "血液型", "メール", "メールアドレス",
    "年齢", "生まれ", "個人", "趣味", "特技"
]

# 個人情報が含まれるか判定
def contains_sensitive_info(text):
    pattern = "|".join(map(re.escape, SENSITIVE_KEYWORDS))
    return re.search(pattern, text, re.IGNORECASE) is not None

# テキストをダミーに置換（マスキング）
def mask_sensitive_data(text):
    mask_map = {}
    for i, word in enumerate(SENSITIVE_KEYWORDS):
        if word in text:
            dummy = f"[[MASK_{i}]]"
            text = text.replace(word, dummy)
            mask_map[dummy] = word
    return text, mask_map

# ダミーを元の語に戻す（アンマスキング）
def unmask_sensitive_data(text, mask_map):
    for dummy, original in mask_map.items():
        text = text.replace(dummy, original)
    return text

# OpenAIで自然な日本語に整形（マスク付き）
def rephrase_with_masked_text(masked_text, system_message="あなたはAIアシスタント愛子です。"):
    prompt = (
        "以下は社内情報の候補です。自然な日本語でまとめてください。ただし個人情報はマスク済みです。\n"
        f"候補情報:\n{masked_text}"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[マスク応答失敗]: {e}"

