"""Bir nechta fayl yig'ib, keyin bitta natija beradigan xizmatlar.

Masalan: PDF birlashtirish, rasmlardan PDF. Foydalanuvchi fayllarni ketma-ket
(yoki albom qilib) yuboradi va «✅ ...» tugmasini bosadi.
"""
import asyncio
import logging
from dataclasses import dataclass
from functools import partial

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import config
from bot.locales import t
from bot.services import archive, image, pdf
from bot.services.runner import Work, execute
from bot.states import CollectStates
from bot.utils import filetypes as ft
from bot.utils.file_store import StoredFile, ref_from_message
from bot.utils.filetypes import human_size

router = Router(name="collect")
logger = logging.getLogger(__name__)

# Albom bo'lib kelgan fayllardan keyin bitta javob berish uchun kutish vaqti
STATUS_DELAY_SECONDS = 0.8


@dataclass(frozen=True)
class Collector:
    accept: frozenset[str] | None  # None — istalgan turdagi fayl
    work: Work
    min_files: int
    max_files: int


COLLECTORS: dict[str, Collector] = {
    "pdf_merge": Collector(frozenset({ft.PDF}), pdf.merge_pdfs, min_files=2, max_files=20),
    "images_to_pdf": Collector(frozenset({ft.IMAGE}), image.images_to_pdf, min_files=1, max_files=50),
    "zip": Collector(None, archive.zip_files, min_files=1, max_files=20),
}

# Bir vaqtda kelgan fayllar ro'yxatni buzmasligi uchun qulf
_locks: dict[int, asyncio.Lock] = {}
_status_tasks: dict[int, asyncio.Task] = {}


class CollectCB(CallbackData, prefix="col"):
    action: str  # done | cancel


def _keyboard(lang: str | None, service: str, count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, f"btn_done_{service}", n=count), callback_data=CollectCB(action="done"))
    kb.button(text=t(lang, "btn_cancel"), callback_data=CollectCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


async def start_collect(
    service: str, callback: CallbackQuery, state: FSMContext, item: StoredFile, bot: Bot, lang: str | None
) -> None:
    files = [[f.file_id, f.file_name] for f in item.files][:COLLECTORS[service].max_files]
    await state.set_state(CollectStates.collecting)
    await state.set_data({"service": service, "files": files})
    await callback.message.edit_text(
        t(lang, f"collect_start_{service}", n=len(files)),
        reply_markup=_keyboard(lang, service, len(files)),
    )


STARTERS = {service: partial(start_collect, service) for service in COLLECTORS}


async def _send_status(message: Message, state: FSMContext, lang: str | None) -> None:
    await asyncio.sleep(STATUS_DELAY_SECONDS)
    data = await state.get_data()
    if "service" not in data:  # bu orada tugatilgan yoki bekor qilingan
        return
    count = len(data["files"])
    try:
        await message.reply(t(lang, "collect_added", n=count), reply_markup=_keyboard(lang, data["service"], count))
    except Exception:
        logger.exception("Yig'ish holatini yuborib bo'lmadi")


def _schedule_status(message: Message, state: FSMContext, lang: str | None) -> None:
    """Oxirgi fayldan keyin bitta javob yuboradi (albomga 10 ta javob emas)."""
    user_id = message.from_user.id
    previous = _status_tasks.get(user_id)
    if previous and not previous.done():
        previous.cancel()
    _status_tasks[user_id] = asyncio.create_task(_send_status(message, state, lang))


@router.message(CollectStates.collecting, F.document | F.photo)
async def collect_add(message: Message, state: FSMContext, lang: str | None) -> None:
    service = (await state.get_data())["service"]
    collector = COLLECTORS[service]
    ref, kind = ref_from_message(message)

    if collector.accept is not None and kind not in collector.accept:
        await message.reply(t(lang, f"collect_wrong_{service}"))
        return
    if ref.file_size > config.max_file_size_mb * 1024 * 1024:
        await message.reply(t(lang, "too_big", max_size=config.max_file_size_mb, size=human_size(ref.file_size)))
        return

    lock = _locks.setdefault(message.from_user.id, asyncio.Lock())
    async with lock:
        files = (await state.get_data()).get("files", [])
        if len(files) >= collector.max_files:
            await message.reply(t(lang, "collect_limit", max=collector.max_files))
            return
        files.append([ref.file_id, ref.file_name])
        await state.update_data(files=files)

    _schedule_status(message, state, lang)


@router.message(CollectStates.collecting)
async def collect_wrong_input(message: Message, state: FSMContext, lang: str | None) -> None:
    service = (await state.get_data())["service"]
    await message.reply(t(lang, f"collect_wrong_{service}"))


@router.callback_query(CollectCB.filter(F.action == "done"), CollectStates.collecting)
async def collect_done(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str | None) -> None:
    data = await state.get_data()
    service, files = data["service"], data.get("files", [])
    collector = COLLECTORS[service]
    if len(files) < collector.min_files:
        await callback.answer(t(lang, "collect_need_more", min=collector.min_files), show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await execute(
        bot, callback.message, callback.from_user.id, service, lang,
        [tuple(f) for f in files], collector.work,
    )


@router.callback_query(CollectCB.filter(F.action == "cancel"), CollectStates.collecting)
async def collect_cancel(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t(lang, "cancelled"))


@router.callback_query(CollectCB.filter())
async def stale_button(callback: CallbackQuery, lang: str | None) -> None:
    await callback.answer(t(lang, "expired"), show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
