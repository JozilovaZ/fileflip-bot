from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import t

CANCEL = "cancel"


class ServiceCB(CallbackData, prefix="svc"):
    service: str
    token: str


def actions_keyboard(lang: str | None, services: list[str], token: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for service in services:
        kb.button(text=t(lang, f"svc_{service}"), callback_data=ServiceCB(service=service, token=token))
    kb.button(text=t(lang, "btn_cancel"), callback_data=ServiceCB(service=CANCEL, token=token))
    kb.adjust(2)
    return kb.as_markup()
