"""Rasm o'lchamini o'zgartirish: tayyor o'lchamlardan birini tanlash yoki o'zi yozish."""
import asyncio
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import t
from bot.services import ServiceError
from bot.services import image
from bot.services.image import ResizeSpec
from bot.services.runner import execute
from bot.states import ResizeStates
from bot.utils import tempfiles
from bot.utils.file_store import FileRef, StoredFile

router = Router(name="image_tools")

# Tayyor o'lchamlar: kalit → (tugma matni kaliti, o'lcham)
PRESETS: dict[str, tuple[str, ResizeSpec]] = {
    "doc": ("btn_resize_doc", image.DOC_3X4),
    "half": ("btn_resize_half", ResizeSpec(percent=50)),
    "w1920": ("btn_resize_w1920", ResizeSpec(width=1920)),
    "w1280": ("btn_resize_w1280", ResizeSpec(width=1280)),
    "w800": ("btn_resize_w800", ResizeSpec(width=800)),
}


class ResizeCB(CallbackData, prefix="resize"):
    action: str  # PRESETS kaliti | cancel


def _resize_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, (text_key, _) in PRESETS.items():
        kb.button(text=t(lang, text_key), callback_data=ResizeCB(action=key))
    kb.button(text=t(lang, "btn_cancel"), callback_data=ResizeCB(action="cancel"))
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup()


async def start_resize(callback: CallbackQuery, state: FSMContext, item: StoredFile, bot: Bot, lang: str | None) -> None:
    await begin_resize(callback.message, state, item.files[0], bot, lang)


async def begin_resize(status: Message, state: FSMContext, ref: FileRef, bot: Bot, lang: str | None) -> None:
    """Rasmning hozirgi o'lchamini aniqlab, foydalanuvchidan yangi o'lchamni so'raydi.

    `status` — bot xabari; savol shu xabarda ko'rsatiladi.
    """
    await status.edit_text(t(lang, "image_reading"))

    workdir = tempfiles.new_workdir()
    try:
        src = workdir / "input"
        await bot.download(ref.file_id, destination=src)
        width, height = await asyncio.to_thread(image.image_size, src)
    except ServiceError as e:
        await status.edit_text(t(lang, e.key, **e.kwargs))
        return
    finally:
        tempfiles.remove(workdir)

    await state.set_state(ResizeStates.waiting_size)
    await state.set_data({"file_id": ref.file_id, "file_name": ref.file_name})
    await status.edit_text(
        t(lang, "resize_ask", name=escape(ref.file_name), width=width, height=height),
        reply_markup=_resize_keyboard(lang),
    )


async def _run_resize(bot: Bot, status: Message, user_id: int, data: dict, spec: ResizeSpec, lang: str | None) -> None:
    async def work(srcs: list[Path], out_dir: Path) -> list[Path]:
        return await image.resize(srcs[0], out_dir, spec)

    await execute(bot, status, user_id, "image_resize", lang, [(data["file_id"], data["file_name"])], work)


@router.message(ResizeStates.waiting_size, F.text)
async def resize_custom(message: Message, state: FSMContext, bot: Bot, lang: str | None) -> None:
    try:
        spec = image.parse_size(message.text)
    except ValueError:
        await message.reply(t(lang, "resize_bad", max=image.RESIZE_MAX_SIDE))
        return

    data = await state.get_data()
    await state.clear()
    status = await message.reply(t(lang, "processing", name=escape(data["file_name"])))
    await _run_resize(bot, status, message.from_user.id, data, spec, lang)


@router.message(ResizeStates.waiting_size)
async def resize_wrong_input(message: Message, lang: str | None) -> None:
    await message.reply(t(lang, "resize_bad", max=image.RESIZE_MAX_SIDE))


@router.callback_query(ResizeCB.filter(F.action == "cancel"), ResizeStates.waiting_size)
async def resize_cancel(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t(lang, "cancelled"))


@router.callback_query(ResizeCB.filter(F.action.in_(PRESETS)), ResizeStates.waiting_size)
async def resize_preset(
    callback: CallbackQuery, callback_data: ResizeCB, state: FSMContext, bot: Bot, lang: str | None
) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    await _run_resize(bot, callback.message, callback.from_user.id, data, PRESETS[callback_data.action][1], lang)


@router.callback_query(ResizeCB.filter())
async def stale_button(callback: CallbackQuery, lang: str | None) -> None:
    await callback.answer(t(lang, "expired"), show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
