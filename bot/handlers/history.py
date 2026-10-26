"""«📂 Mening fayllarim»: foydalanuvchining oxirgi natijalari va ularni qayta olish."""
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import db
from bot.locales import all_variants, t
from bot.services.runner import CAPTION
from bot.utils.filetypes import human_size

router = Router(name="history")

CLEAR = 0
# Sanalar O'zbekiston vaqtida ko'rsatiladi
LOCAL_TZ = timezone(timedelta(hours=5))
MAX_NAME_LEN = 28


class HistoryCB(CallbackData, prefix="hist"):
    item_id: int


def _short(name: str) -> str:
    return name if len(name) <= MAX_NAME_LEN else name[:MAX_NAME_LEN - 1] + "…"


def _history_keyboard(lang: str | None, items: list[tuple[int, str, str, int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item_id, _, name, size, created_at in items:
        date = datetime.fromisoformat(created_at).astimezone(LOCAL_TZ).strftime("%d.%m %H:%M")
        kb.button(text=f"📄 {_short(name)} · {human_size(size)} · {date}", callback_data=HistoryCB(item_id=item_id))
    kb.button(text=t(lang, "history_clear"), callback_data=HistoryCB(item_id=CLEAR))
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("history"))
@router.message(F.text.in_(all_variants("btn_history")))
async def cmd_history(message: Message, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    items = await db.get_history(message.from_user.id)
    if not items:
        await message.answer(t(lang, "history_empty"))
        return
    await message.answer(t(lang, "history_title", n=len(items)), reply_markup=_history_keyboard(lang, items))


@router.callback_query(HistoryCB.filter(F.item_id == CLEAR))
async def on_clear(callback: CallbackQuery, lang: str | None) -> None:
    await db.clear_history(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text(t(lang, "history_cleared"))


@router.callback_query(HistoryCB.filter())
async def on_item(callback: CallbackQuery, callback_data: HistoryCB, lang: str | None) -> None:
    file_id = await db.get_history_file_id(callback.from_user.id, callback_data.item_id)
    if file_id is None:
        await callback.answer(t(lang, "history_missing"), show_alert=True)
        return
    await callback.answer()
    await callback.message.answer_document(file_id, caption=CAPTION)
