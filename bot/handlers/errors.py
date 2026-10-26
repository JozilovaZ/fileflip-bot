import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

from bot.locales import t

router = Router(name="errors")
logger = logging.getLogger(__name__)

# Zararsiz xatolar: bot o'chiq paytida bosilgan eski tugmalar, o'zgarmagan xabarni tahrirlash va h.k.
_HARMLESS = (
    "query is too old",
    "message is not modified",
    "message to edit not found",
    "message to delete not found",
)


@router.errors()
async def on_error(event: ErrorEvent, lang: str | None = None) -> None:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest) and any(s in str(exc) for s in _HARMLESS):
        logger.info("Zararsiz xato o'tkazib yuborildi: %s", exc)
        return

    logger.error("Kutilmagan xato: %s", exc, exc_info=exc)

    update = event.update
    try:
        if update.message:
            await update.message.answer(t(lang, "error"))
        elif update.callback_query:
            await update.callback_query.answer(t(lang, "error"), show_alert=True)
    except Exception as e:
        logger.warning("Foydalanuvchiga xato haqida xabar yuborib bo'lmadi: %s", e)
