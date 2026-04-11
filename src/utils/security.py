import re

def sanitize_input(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[<>]", "", text)
    return text
