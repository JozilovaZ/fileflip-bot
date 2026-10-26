import asyncio
import logging
import shutil
import time
import uuid
from pathlib import Path

from bot.config import config

logger = logging.getLogger(__name__)

MAX_AGE_SECONDS = 60 * 60
CLEANUP_INTERVAL_SECONDS = 10 * 60


def new_workdir() -> Path:
    """Har bir vazifa uchun alohida vaqtinchalik papka yaratadi."""
    path = config.temp_dir / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def remove(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def clear_all() -> None:
    for item in config.temp_dir.iterdir():
        remove(item) if item.is_dir() else item.unlink(missing_ok=True)


def cleanup_old() -> int:
    deadline = time.time() - MAX_AGE_SECONDS
    removed = 0
    for item in config.temp_dir.iterdir():
        if item.stat().st_mtime < deadline:
            remove(item) if item.is_dir() else item.unlink(missing_ok=True)
            removed += 1
    return removed


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            removed = cleanup_old()
            if removed:
                logger.info("Eski vaqtinchalik fayllar o'chirildi: %d", removed)
        except Exception:
            logger.exception("Vaqtinchalik fayllarni tozalashda xato")
