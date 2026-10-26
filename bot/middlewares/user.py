from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.database import db


class UserMiddleware(BaseMiddleware):
    """Har bir so'rovda foydalanuvchini bazaga yozadi va handlerlarga `lang` ni uzatadi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        data["lang"] = None
        if user and not user.is_bot:
            data["lang"] = await db.upsert_user(user.id, user.full_name, user.username)
        return await handler(event, data)
