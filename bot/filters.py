from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject, User

from bot.config import config


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, event_from_user: User | None = None) -> bool:
        return event_from_user is not None and event_from_user.id in config.admin_ids
