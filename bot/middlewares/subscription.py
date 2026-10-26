import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, TelegramObject, User
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import config
from bot.database import settings
from bot.locales import t

logger = logging.getLogger(__name__)

SUB_CHECK = "sub:check"
# Obuna tasdiqlangan foydalanuvchini qayta tekshirmaslik vaqti
OK_CACHE_SECONDS = 5 * 60
# Albom kelganda obuna xabari bir necha marta chiqmasligi uchun
PROMPT_COOLDOWN_SECONDS = 3
_SUBSCRIBED = {"creator", "administrator", "member", "restricted"}


def sub_keyboard(lang: str | None, channels: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.button(text=f"📢 {ch['title']}", url=ch["url"])
    kb.button(text=t(lang, "btn_sub_check"), callback_data=SUB_CHECK)
    kb.adjust(1)
    return kb.as_markup()


async def missing_channels(bot: Bot, user_id: int) -> list[dict]:
    missing = []
    for ch in settings.channels():
        try:
            member = await bot.get_chat_member(ch["id"], user_id)
        except Exception:
            # bot kanaldan chiqarilgan bo'lsa — foydalanuvchini to'smaymiz
            logger.warning("Kanal obunasini tekshirib bo'lmadi: %s", ch)
            continue
        if member.status not in _SUBSCRIBED:
            missing.append(ch)
    return missing


class SubscriptionMiddleware(BaseMiddleware):
    """Majburiy obuna yoqilgan bo'lsa, kanalga a'zo bo'lmaganlarni to'xtatadi."""

    def __init__(self) -> None:
        self._ok_until: dict[int, float] = {}
        self._last_prompt: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if (
            user is None
            or user.id in config.admin_ids
            or not settings.sub_enabled()
            or not settings.channels()
            or (isinstance(event, CallbackQuery) and (event.data or "").startswith("lang:"))
            or self._ok_until.get(user.id, 0) > time.time()
        ):
            return await handler(event, data)

        bot: Bot = data["bot"]
        lang = data.get("lang")
        missing = await missing_channels(bot, user.id)
        if not missing:
            self._ok_until[user.id] = time.time() + OK_CACHE_SECONDS
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == SUB_CHECK:
            await event.answer(t(lang, "sub_not_yet"), show_alert=True)
            return None
        if isinstance(event, CallbackQuery):
            await event.answer()

        now = time.time()
        if now - self._last_prompt.get(user.id, 0) > PROMPT_COOLDOWN_SECONDS:
            self._last_prompt[user.id] = now
            await bot.send_message(user.id, t(lang, "sub_required"), reply_markup=sub_keyboard(lang, missing))
        return None
