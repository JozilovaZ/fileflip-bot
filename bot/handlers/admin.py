"""Admin panel: statistika, hammaga xabar yuborish, majburiy obuna.

Panel faqat o'zbek tilida — u faqat bot egalari uchun.
"""
import asyncio
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database import db, settings
from bot.filters import IsAdmin
from bot.locales import LANGUAGES
from bot.states import AdminStates

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
logger = logging.getLogger(__name__)

# Telegram cheklovi: sekundiga ~30 xabar. Xavfsiz tezlik bilan yuboramiz.
BROADCAST_DELAY_SECONDS = 0.05
BROADCAST_PROGRESS_EVERY = 25

SERVICE_NAMES = {
    "word_to_pdf": "Word → PDF",
    "ppt_to_pdf": "PowerPoint → PDF",
    "excel_to_pdf": "Excel → PDF",
    "pdf_to_word": "PDF → Word",
    "pdf_to_images": "PDF → rasmlar",
    "pdf_compress": "PDF siqish",
    "pdf_merge": "PDF birlashtirish",
    "pdf_split": "PDF ajratish",
    "images_to_pdf": "Rasmlar → PDF",
    "image_compress": "Rasm siqish",
    "zip": "ZIP qilish",
    "unzip": "ZIP ochish",
}

_broadcast_task: asyncio.Task | None = None


class AdminCB(CallbackData, prefix="adm"):
    action: str
    arg: str = ""


def _btn(kb: InlineKeyboardBuilder, text: str, action: str, arg: str = "") -> None:
    kb.button(text=text, callback_data=AdminCB(action=action, arg=arg))


def _menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "📊 Statistika", "stats")
    _btn(kb, "📣 Xabar yuborish", "broadcast")
    _btn(kb, "📢 Majburiy obuna", "sub")
    kb.adjust(1)
    return kb.as_markup()


def _back_keyboard(action: str = "menu") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "⬅️ Orqaga", action)
    return kb.as_markup()


MENU_TEXT = "🛠 <b>FileFlip — admin panel</b>\n\nKerakli bo'limni tanlang 👇"


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=_menu_keyboard())


@router.callback_query(AdminCB.filter(F.action == "menu"))
async def on_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(MENU_TEXT, reply_markup=_menu_keyboard())


# ---------- Statistika ----------

def _stats_text(s: dict) -> str:
    langs = "\n".join(f"   {LANGUAGES.get(code, '❔ tanlanmagan')}: {n}" for code, n in s["langs"]) or "   —"
    services = "\n".join(
        f"   {SERVICE_NAMES.get(name, name)}: <b>{total}</b> (24 soatda: {day or 0})"
        for name, total, day in s["services"]
    ) or "   —"
    success = (
        round((s["ops_total"] - s["ops_failed"]) / s["ops_total"] * 100) if s["ops_total"] else 100
    )
    return (
        "📊 <b>Statistika</b>\n\n"
        "👥 <b>Foydalanuvchilar</b>\n"
        f"   Jami: <b>{s['users_total']}</b>\n"
        f"   Botni bloklagan: {s['users_blocked']}\n"
        f"   Yangi: 24 soat — {s['new_day']}, 7 kun — {s['new_week']}, 30 kun — {s['new_month']}\n"
        f"   Faol: 24 soat — {s['active_day']}, 7 kun — {s['active_week']}\n\n"
        f"🌐 <b>Tillar</b>\n{langs}\n\n"
        "⚙️ <b>Bajarilgan amallar</b>\n"
        f"   Jami: <b>{s['ops_total']}</b> (24 soatda: {s['ops_day']})\n"
        f"   Muvaffaqiyatli: {success}%\n\n"
        f"🏆 <b>Xizmatlar reytingi</b>\n{services}"
    )


@router.callback_query(AdminCB.filter(F.action == "stats"))
async def on_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    kb = InlineKeyboardBuilder()
    _btn(kb, "🔄 Yangilash", "stats")
    _btn(kb, "⬅️ Orqaga", "menu")
    kb.adjust(2)
    try:
        await callback.message.edit_text(_stats_text(await db.get_stats()), reply_markup=kb.as_markup())
    except TelegramBadRequest:
        pass  # ma'lumot o'zgarmagan bo'lsa Telegram xato qaytaradi


# ---------- Xabar yuborish (rassilka) ----------

@router.callback_query(AdminCB.filter(F.action == "broadcast"))
async def on_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if _broadcast_task and not _broadcast_task.done():
        await callback.message.edit_text("⏳ Avvalgi xabar hali yuborilmoqda. Tugashini kuting.", reply_markup=_back_keyboard())
        return
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.edit_text(
        "📣 <b>Hammaga xabar yuborish</b>\n\n"
        "Yubormoqchi bo'lgan xabaringizni jo'nating: matn, rasm, video, fayl — istalgan ko'rinishda.\n"
        "Xabar foydalanuvchilarga xuddi shu holida boradi.",
        reply_markup=_back_keyboard(),
    )


@router.message(AdminStates.broadcast_message)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    total = len(await db.get_active_user_ids())
    await state.set_state(AdminStates.broadcast_confirm)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)

    kb = InlineKeyboardBuilder()
    _btn(kb, f"✅ Yuborish ({total} kishi)", "broadcast_go")
    _btn(kb, "❌ Bekor qilish", "menu")
    kb.adjust(1)
    await message.copy_to(message.chat.id)
    await message.answer("👆 Xabar shunday ko'rinadi. Yuboraymi?", reply_markup=kb.as_markup())


@router.callback_query(AdminCB.filter(F.action == "broadcast_go"), AdminStates.broadcast_confirm)
async def broadcast_go(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    global _broadcast_task
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if _broadcast_task and not _broadcast_task.done():
        await callback.message.edit_text("⏳ Avvalgi xabar hali yuborilmoqda.")
        return
    status = await callback.message.edit_text("📣 Yuborish boshlandi...")
    _broadcast_task = asyncio.create_task(_broadcast(bot, status, data["chat_id"], data["message_id"]))


async def _copy_with_retry(bot: Bot, user_id: int, from_chat_id: int, message_id: int) -> None:
    while True:
        try:
            await bot.copy_message(user_id, from_chat_id, message_id)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)


async def _broadcast(bot: Bot, status: Message, from_chat_id: int, message_id: int) -> None:
    user_ids = await db.get_active_user_ids()
    sent = blocked = failed = 0

    async def report(final: bool) -> None:
        head = "✅ <b>Yuborish tugadi</b>" if final else "📣 <b>Yuborilmoqda...</b>"
        text = (
            f"{head}\n\n"
            f"👥 Jami: {len(user_ids)}\n"
            f"✅ Yetkazildi: {sent}\n"
            f"🚫 Botni bloklagan: {blocked}\n"
            f"⚠️ Xato: {failed}"
        )
        try:
            await status.edit_text(text, reply_markup=_back_keyboard() if final else None)
        except TelegramBadRequest:
            pass

    for i, user_id in enumerate(user_ids, 1):
        try:
            await _copy_with_retry(bot, user_id, from_chat_id, message_id)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            await db.mark_blocked(user_id)
        except Exception:
            failed += 1
            logger.warning("Xabar yuborilmadi: %s", user_id, exc_info=True)
        if i % BROADCAST_PROGRESS_EVERY == 0:
            await report(final=False)
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    await report(final=True)


# ---------- Majburiy obuna ----------

def _sub_view() -> tuple[str, InlineKeyboardMarkup]:
    enabled = settings.sub_enabled()
    channels = settings.channels()
    lines = "\n".join(f"{i}. <a href=\"{ch['url']}\">{escape(ch['title'])}</a>" for i, ch in enumerate(channels, 1))
    status = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"
    text = (
        "📢 <b>Majburiy obuna</b>\n\n"
        f"Holat: {status}\n\n"
        f"<b>Kanallar:</b>\n{lines or 'Hali kanal qo‘shilmagan'}\n\n"
        "ℹ️ Bot har bir kanalda <b>admin</b> bo'lishi kerak — aks holda obunani tekshira olmaydi."
    )
    kb = InlineKeyboardBuilder()
    _btn(kb, "🔴 O'chirish" if enabled else "🟢 Yoqish", "sub_toggle")
    _btn(kb, "➕ Kanal qo'shish", "sub_add")
    for i, ch in enumerate(channels):
        _btn(kb, f"🗑 {ch['title']}", "sub_del", str(i))
    _btn(kb, "⬅️ Orqaga", "menu")
    kb.adjust(2, 1)
    return text, kb.as_markup()


async def _show_sub(message: Message, edit: bool = True) -> None:
    text, markup = _sub_view()
    if edit:
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(AdminCB.filter(F.action == "sub"))
async def on_sub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _show_sub(callback.message)


@router.callback_query(AdminCB.filter(F.action == "sub_toggle"))
async def on_sub_toggle(callback: CallbackQuery) -> None:
    if not settings.sub_enabled() and not settings.channels():
        await callback.answer("Avval kamida bitta kanal qo'shing.", show_alert=True)
        return
    await settings.set_sub_enabled(not settings.sub_enabled())
    await callback.answer("✅ Saqlandi")
    await _show_sub(callback.message)


@router.callback_query(AdminCB.filter(F.action == "sub_del"))
async def on_sub_delete(callback: CallbackQuery, callback_data: AdminCB) -> None:
    channels = settings.channels()
    index = int(callback_data.arg)
    if 0 <= index < len(channels):
        channels.pop(index)
        await settings.set_channels(channels)
        if not channels:
            await settings.set_sub_enabled(False)
    await callback.answer("🗑 O'chirildi")
    await _show_sub(callback.message)


@router.callback_query(AdminCB.filter(F.action == "sub_add"))
async def on_sub_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.channel_add)
    await callback.answer()
    await callback.message.edit_text(
        "➕ <b>Kanal qo'shish</b>\n\n"
        "1. Botni kanalga <b>admin</b> qilib qo'shing.\n"
        "2. Keyin quyidagilardan birini yuboring:\n"
        "   • kanal username: <code>@kanal_nomi</code>\n"
        "   • kanal havolasi: <code>https://t.me/kanal_nomi</code>\n"
        "   • kanal ID si: <code>-1001234567890</code>\n"
        "   • yoki kanaldan istalgan postni shu yerga forward qiling",
        reply_markup=_back_keyboard("sub"),
    )


def _channel_ref(message: Message) -> int | str | None:
    origin = message.forward_origin
    if origin is not None and origin.type == "channel":
        return origin.chat.id
    text = (message.text or "").strip()
    if re.fullmatch(r"-100\d+", text):
        return int(text)
    match = re.fullmatch(r"(?:https?://)?(?:t\.me/|@)([A-Za-z0-9_]{4,})/?", text)
    return f"@{match[1]}" if match else None


@router.message(AdminStates.channel_add)
async def channel_add(message: Message, state: FSMContext, bot: Bot) -> None:
    ref = _channel_ref(message)
    if ref is None:
        await message.reply("⚠️ Tushunmadim. <code>@kanal_nomi</code> ko'rinishida yuboring yoki kanaldan post forward qiling.")
        return

    try:
        chat = await bot.get_chat(ref)
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramBadRequest:
        await message.reply("❌ Kanal topilmadi yoki bot unga qo'shilmagan. Botni kanalga admin qilib qo'shing.")
        return

    if me.status != "administrator":
        await message.reply("❌ Bot bu kanalda admin emas. Avval botni kanalga admin qiling.")
        return

    channels = settings.channels()
    if any(ch["id"] == chat.id for ch in channels):
        await message.reply("ℹ️ Bu kanal allaqachon ro'yxatda bor.")
        return

    if chat.username:
        url = f"https://t.me/{chat.username}"
    else:
        url = chat.invite_link or await bot.export_chat_invite_link(chat.id)

    channels.append({"id": chat.id, "title": chat.title or str(chat.id), "url": url})
    await settings.set_channels(channels)
    await state.clear()
    await message.reply(f"✅ <b>{escape(chat.title or '')}</b> qo'shildi.")
    await _show_sub(message, edit=False)
