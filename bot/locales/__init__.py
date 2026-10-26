from bot.locales.texts import TEXTS

DEFAULT_LANG = "uz"

LANGUAGES = {
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}


def t(lang: str | None, key: str, **kwargs) -> str:
    texts = TEXTS.get(lang or DEFAULT_LANG, TEXTS[DEFAULT_LANG])
    text = texts.get(key) or TEXTS[DEFAULT_LANG][key]
    return text.format(**kwargs) if kwargs else text


def all_variants(key: str) -> set[str]:
    """Kalitning barcha tillardagi matnlari (menyu tugmalarini ushlash uchun)."""
    return {texts[key] for texts in TEXTS.values() if key in texts}
