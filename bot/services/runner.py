import asyncio
import logging
import time
from html import escape
from pathlib import Path
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputMediaDocument, Message
from aiogram.utils.chat_action import ChatActionSender

from bot.database import db
from bot.locales import t
from bot.services import COMPRESS_SERVICES, SERVICES, ServiceError
from bot.utils import tempfiles
from bot.utils.file_store import StoredFile
from bot.utils.filetypes import human_size, safe_filename

logger = logging.getLogger(__name__)

CAPTION = "🔄 @File_UzFlip_bot"
ALBUM_SIZE = 10
# Telegram bot 50 MB dan katta fayl yubora olmaydi
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Navbat: bir vaqtda bajariladigan og'ir ishlar soni (server yuklamasini cheklaydi)
MAX_CONCURRENT_JOBS = 3
# Bitta foydalanuvchining navbatdagi + bajarilayotgan ishlari soni
MAX_USER_PENDING = 5

_jobs = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
# har bir foydalanuvchining ishlari ketma-ket bajariladi — bitta odam navbatni egallab olmasligi uchun
_user_locks: dict[int, asyncio.Lock] = {}
_user_pending: dict[int, int] = {}

# Kirish fayllari ro'yxatini oladi va tayyor fayllarni qaytaradi
Work = Callable[[list[Path], Path], Awaitable[list[Path]]]


async def _edit(status: Message, text: str) -> None:
    """Holat xabarini yangilaydi. Matn o'zgarmagan bo'lsa (masalan, menyudan kelganda
    xabar allaqachon "ishlanmoqda" deb turgan bo'lsa), Telegram xatosini e'tiborsiz qoldiradi —
    aks holda ish boshlanmasdan to'xtab qoladi."""
    try:
        await status.edit_text(text)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _send_outputs(status: Message, outputs: list[Path]) -> list[tuple[str, str, int]]:
    """Fayllarni yuboradi va Telegram bergan (file_id, nom, hajm) larni qaytaradi."""
    if len(outputs) == 1:
        sent = [await status.answer_document(FSInputFile(outputs[0]), caption=CAPTION)]
    else:
        sent = []
        for i in range(0, len(outputs), ALBUM_SIZE):
            chunk = outputs[i:i + ALBUM_SIZE]
            # aiogram obyektlari o'zgarmas (frozen) — izoh yaratish paytida beriladi
            media = [
                InputMediaDocument(media=FSInputFile(p), caption=CAPTION if p == chunk[-1] else None)
                for p in chunk
            ]
            sent += await status.answer_media_group(media)
    return [
        (m.document.file_id, path.name, m.document.file_size or path.stat().st_size)
        for m, path in zip(sent, outputs)
        if m.document
    ]


def _done_text(lang: str | None, service: str, srcs: list[Path], outputs: list[Path]) -> str:
    if service in COMPRESS_SERVICES and len(srcs) == len(outputs) == 1:
        before, after = srcs[0].stat().st_size, outputs[0].stat().st_size
        return t(
            lang,
            "done_compressed",
            before=human_size(before),
            after=human_size(after),
            percent=round((1 - after / before) * 100),
        )
    return t(lang, "done")


async def execute(
    bot: Bot,
    status: Message,
    user_id: int,
    service: str,
    lang: str | None,
    files: list[tuple[str, str]],
    work: Work,
) -> None:
    """Ishni navbatga qo'yadi, keyin fayllarni (file_id, nom) yuklab oladi,
    `work` ni bajaradi va natijani yuboradi.

    `status` — bot xabari; jarayon holati shu xabarda ko'rsatiladi.
    """
    if _user_pending.get(user_id, 0) >= MAX_USER_PENDING:
        await _edit(status, t(lang, "too_many_jobs", max=MAX_USER_PENDING))
        return

    _user_pending[user_id] = _user_pending.get(user_id, 0) + 1
    user_lock = _user_locks.setdefault(user_id, asyncio.Lock())
    try:
        if user_lock.locked() or _jobs.locked():
            await _edit(status, t(lang, "queued"))
        async with user_lock, _jobs:
            await _process(bot, status, user_id, service, lang, files, work)
    finally:
        _user_pending[user_id] -= 1
        if not _user_pending[user_id]:
            del _user_pending[user_id]
            _user_locks.pop(user_id, None)


async def _process(
    bot: Bot,
    status: Message,
    user_id: int,
    service: str,
    lang: str | None,
    files: list[tuple[str, str]],
    work: Work,
) -> None:
    label = escape(files[0][1]) if len(files) == 1 else t(lang, "n_files", n=len(files))
    await _edit(status, t(lang, "processing", name=label))
    workdir = tempfiles.new_workdir()
    success = False
    started = time.monotonic()
    # bosqichlar vaqti: yuklab olish / konvertatsiya / yuborish
    timings: dict[str, float] = {}
    try:
        async with ChatActionSender.upload_document(bot=bot, chat_id=status.chat.id):
            srcs: list[Path] = []
            for i, (file_id, name) in enumerate(files):
                # har bir fayl alohida papkada — bir xil nomlar to'qnashmasligi uchun
                folder = workdir / "in" / f"{i:03d}"
                folder.mkdir(parents=True)
                src = folder / safe_filename(name)
                await bot.download(file_id, destination=src)
                srcs.append(src)
            timings["yuklash"] = time.monotonic() - started

            out_dir = workdir / "out"
            out_dir.mkdir()
            step = time.monotonic()
            outputs = await work(srcs, out_dir)
            timings["ish"] = time.monotonic() - step
            if any(p.stat().st_size > MAX_UPLOAD_BYTES for p in outputs):
                raise ServiceError("result_too_big")
            step = time.monotonic()
            sent = await _send_outputs(status, outputs)
            timings["yuborish"] = time.monotonic() - step

        success = True
        await db.add_history(user_id, service, sent)
        await _edit(status, _done_text(lang, service, srcs, outputs))
    except ServiceError as e:
        await _edit(status, t(lang, e.key, **e.kwargs))
    except Exception:
        logger.exception("Xizmat bajarilmadi: %s (%s)", service, [name for _, name in files])
        await _edit(status, t(lang, "error"))
    finally:
        tempfiles.remove(workdir)
        await db.log_service(user_id, service, success)
        logger.info(
            "%s | user=%s | fayllar=%d | %s | %.1fs (%s)",
            service, user_id, len(files), "OK" if success else "XATO", time.monotonic() - started,
            ", ".join(f"{k} {v:.1f}s" for k, v in timings.items()),
        )


async def run_service(bot: Bot, status: Message, item: StoredFile, service: str, lang: str | None) -> None:
    """Bitta faylli oddiy xizmatni bajaradi (SERVICES ro'yxatidan)."""
    func = SERVICES[service]
    ref = item.files[0]

    async def work(srcs: list[Path], out_dir: Path) -> list[Path]:
        return await func(srcs[0], out_dir)

    await execute(bot, status, item.user_id, service, lang, [(ref.file_id, ref.file_name)], work)
