"""Admin sozlamalari (majburiy obuna). Tez o'qish uchun xotirada saqlanadi."""
import json

from bot.database import db

_SUB_ENABLED = "sub_enabled"
_CHANNELS = "required_channels"

_cache: dict = {"sub_enabled": False, "channels": []}


async def load() -> None:
    _cache["sub_enabled"] = (await db.get_setting(_SUB_ENABLED)) == "1"
    _cache["channels"] = json.loads(await db.get_setting(_CHANNELS) or "[]")


def sub_enabled() -> bool:
    return _cache["sub_enabled"]


def channels() -> list[dict]:
    """Har bir kanal: {"id": int, "title": str, "url": str}."""
    return list(_cache["channels"])


async def set_sub_enabled(enabled: bool) -> None:
    await db.set_setting(_SUB_ENABLED, "1" if enabled else "0")
    _cache["sub_enabled"] = enabled


async def set_channels(items: list[dict]) -> None:
    await db.set_setting(_CHANNELS, json.dumps(items, ensure_ascii=False))
    _cache["channels"] = list(items)
