"""TTS 文本预处理与语速转换。"""

from __future__ import annotations

import re

PUNCTUATIONS = [
    "?",
    ",",
    ".",
    "、",
    ";",
    ":",
    "!",
    "…",
    "？",
    "，",
    "。",
    "；",
    "：",
    "！",
    "...",
    "،",
    "؛",
    "؟",
]


def convert_rate_to_percent(rate: float) -> str:
    percent = round((rate - 1.0) * 100)
    if percent >= 0:
        return f"+{percent}%"
    return f"{percent}%"


def split_string_by_punctuations(text: str) -> list[str]:
    result: list[str] = []
    txt = ""
    s = text or ""
    for i, char in enumerate(s):
        if char == "\n":
            result.append(txt.strip())
            txt = ""
            continue
        previous_char = s[i - 1] if i > 0 else ""
        next_char = s[i + 1] if i < len(s) - 1 else ""
        if char == "." and previous_char.isdigit() and next_char.isdigit():
            txt += char
            continue
        if char == "," and previous_char.isdigit() and next_char.isdigit():
            txt += char
            continue
        if char not in PUNCTUATIONS:
            txt += char
        else:
            result.append(txt.strip())
            txt = ""
    result.append(txt.strip())
    return [part for part in result if part]


def normalize_script_text(text: str) -> str:
    """清理 Markdown/括号等 TTS 不应朗读的字符。"""
    cleaned = (text or "").replace("[", " ").replace("]", " ")
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
