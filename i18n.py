"""Tiny translation layer. English is the master text and the fallback."""
from __future__ import annotations

from locales_a import PACK as _PACK_A
from locales_b import PACK as _PACK_B
from locales_c import PACK as _PACK_C

# code -> name shown in the language menu (always in the language's own script)
LANGUAGES: dict[str, str] = {
    "en": "English",
    "id": "Bahasa Indonesia",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "it": "Italiano",
    "ru": "Русский",
    "tr": "Türkçe",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "ja": "日本語",
    "ko": "한국어",
    "zh": "简体中文",
}

STRINGS: dict[str, dict[str, str]] = {**_PACK_A, **_PACK_B, **_PACK_C}
DEFAULT = "en"
_current = DEFAULT


def set_language(code: str) -> None:
    global _current
    _current = code if code in STRINGS else DEFAULT


def get_language() -> str:
    return _current


def t(key: str, **params) -> str:
    text = STRINGS.get(_current, {}).get(key) or STRINGS[DEFAULT].get(key) or key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return STRINGS[DEFAULT][key].format(**params) if key in STRINGS[DEFAULT] else text
    return text
