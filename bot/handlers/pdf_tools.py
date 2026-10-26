"""PDF ajratish: sahifalarni tanlash yoki har bir sahifani alohida faylga ajratish."""
import asyncio
import re
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import t
from bot.services import ServiceError
from bot.services import pdf
from bot.services.runner import execute
from bot.states import SplitStates
from bot.utils import tempfiles
from bot.utils.file_store import FileRef, StoredFile

router = Router(name="pdf_tools")


class SplitCB(CallbackData, prefix="split"):
    action: str  # all | cancel


def _split_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_split_all"), callback_data=SplitCB(action="all"))
    kb.button(text=t(lang, "btn_cancel"), callback_data=SplitCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


async def start_split(callback: CallbackQuery, state: FSMContext, item: StoredFile, bot: Bot, lang: str | None) -> None:
    await begin_split(callback.message, state, item.files[0], bot, lang)


async def begin_split(status: Message, state: FSMContext, ref: FileRef, bot: Bot, lang: str | None) -> None:
    """PDF sahifalar sonini aniqlab, foydalanuvchidan kerakli sahifalarni so'raydi.

    `status` — bot xabari; savol shu xabarda ko'rsatiladi.
    """
    await status.edit_text(t(lang, "pdf_reading"))

    workdir = tempfiles.new_workdir()
    try:
        src = workdir / "input.pdf"
        await bot.download(ref.file_id, destination=src)
        pages = await asyncio.to_thread(pdf.page_count, src)
    except ServiceError as e:
        await status.edit_text(t(lang, e.key, **e.kwargs))
        return
    finally:
        tempfiles.remove(workdir)

    await state.set_state(SplitStates.waiting_pages)
    await state.set_data({"file_id": ref.file_id, "file_name": ref.file_name, "pages": pages})
    await status.edit_text(
        t(lang, "split_ask", name=escape(ref.file_name), pages=pages),
        reply_markup=_split_keyboard(lang),
    )


@router.message(SplitStates.waiting_pages, F.text)
async def split_pages(message: Message, state: FSMContext, bot: Bot, lang: str | None) -> None:
    data = await state.get_data()
    try:
        pages = pdf.parse_pages(message.text, data["pages"])
    except ValueError:
        await message.reply(t(lang, "split_bad", pages=data["pages"]))
        return

    await state.clear()
    label = re.sub(r"[^\d,-]", "", re.sub(r"\s*[-–—]\s*", "-", message.text))[:40].strip(",")

    async def work(srcs: list[Path], out_dir: Path) -> list[Path]:
        return await pdf.extract_pages(srcs[0], out_dir, pages, label)

    status = await message.reply(t(lang, "processing", name=escape(data["file_name"])))
    await execute(
        bot, status, message.from_user.id, "pdf_split", lang,
        [(data["file_id"], data["file_name"])], work,
    )


@router.message(SplitStates.waiting_pages)
async def split_wrong_input(message: Message, state: FSMContext, lang: str | None) -> None:
    pages = (await state.get_data()).get("pages", 0)
    await message.reply(t(lang, "split_bad", pages=pages))


@router.callback_query(SplitCB.filter(F.action == "all"), SplitStates.waiting_pages)
async def split_all(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()

    async def work(srcs: list[Path], out_dir: Path) -> list[Path]:
        return await pdf.split_all(srcs[0], out_dir)

    await execute(
        bot, callback.message, callback.from_user.id, "pdf_split", lang,
        [(data["file_id"], data["file_name"])], work,
    )


@router.callback_query(SplitCB.filter(F.action == "cancel"), SplitStates.waiting_pages)
async def split_cancel(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t(lang, "cancelled"))


@router.callback_query(SplitCB.filter())
async def stale_button(callback: CallbackQuery, lang: str | None) -> None:
    await callback.answer(t(lang, "expired"), show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
