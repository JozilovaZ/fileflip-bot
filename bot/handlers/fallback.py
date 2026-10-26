from aiogram import Router
from aiogram.types import Message

from bot.keyboards.common import main_menu
from bot.locales import t

router = Router(name="fallback")


@router.message()
async def any_message(message: Message, lang: str | None) -> None:
    await message.answer(t(lang, "send_file"), reply_markup=main_menu(lang))
