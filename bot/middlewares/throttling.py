import time
from collections import deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, TelegramObject, User

from bot.config import config
from bot.locales import t

# Bir foydalanuvchi PERIOD soniya ichida ko'pi bilan LIMIT ta so'rov yubora oladi.
# 10 talik albom ham bemalol sig'adi.
LIMIT = 30
PERIOD_SECONDS = 60


class ThrottlingMiddleware(BaseMiddleware):
    """Spamga qarshi himoya: juda ko'p so'rov yuborgan foydalanuvchini vaqtincha to'xtatadi."""

    def __init__(self) -> None:
        self._events: dict[int, deque[float]] = {}
        self._warned_at: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.id in config.admin_ids:
            return await handler(event, data)

        now = time.monotonic()
        events = self._events.setdefault(user.id, deque())
        while events and now - events[0] > PERIOD_SECONDS:
            events.popleft()

        if len(events) < LIMIT:
            events.append(now)
            return await handler(event, data)

        lang = data.get("lang")
        if isinstance(event, CallbackQuery):
            await event.answer(t(lang, "throttled"))
        elif now - self._warned_at.get(user.id, 0) > PERIOD_SECONDS:
            # ogohlantirishni har daqiqada bir martadan ko'p yubormaymiz
            self._warned_at[user.id] = now
            bot: Bot = data["bot"]
            await bot.send_message(user.id, t(lang, "throttled"))
        return None
