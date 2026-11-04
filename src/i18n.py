"""Hebrew / English UI strings. T('key') returns the string for the current language."""

LANG = "he"

S = {}  # filled below: key -> (hebrew, english)


def set_lang(lang: str):
    global LANG
    LANG = "he" if lang == "he" else "en"


def T(key: str, *args) -> str:
    pair = S.get(key)
    s = key if pair is None else pair[0 if LANG == "he" else 1]
    return s.format(*args) if args else s
