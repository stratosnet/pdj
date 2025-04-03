def mask_secret(text: str, keep_first=4):
    if len(text) > keep_first:
        text = text[:4] + "*" * (len(text) - keep_first)
    return text
