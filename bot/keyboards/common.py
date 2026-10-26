from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import LANGUAGES, t


def lang_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, title in LANGUAGES.items():
        kb.button(text=title, callback_data=f"lang:{code}")
    kb.adjust(1)
    return kb.as_markup()


def main_menu(lang: str | None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_services")), KeyboardButton(text=t(lang, "btn_history"))],
            [KeyboardButton(text=t(lang, "btn_lang")), KeyboardButton(text=t(lang, "btn_help"))],
        ],
        resize_keyboard=True,
        input_field_placeholder="FileFlip 🔄",
    )
