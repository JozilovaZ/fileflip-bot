import asyncio
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.handlers import collect, pdf_tools
from bot.keyboards.files import CANCEL, ServiceCB, actions_keyboard
from bot.locales import t
from bot.services import ACTIONS, MULTI_ACTIONS, SERVICES
from bot.services.runner import run_service
from bot.utils import file_store
from bot.utils import filetypes as ft
from bot.utils.file_store import FileRef, StoredFile, ref_from_message

router = Router(name="files")

# Albomdagi barcha fayllar kelishini kutish vaqti
ALBUM_WAIT_SECONDS = 1.0

# Ko'p bosqichli xizmatlar: tugma bosilganda shu funksiyalar ishga tushadi
INTERACTIVE = {
    **collect.STARTERS,
    "pdf_split": pdf_tools.start_split,
}

_albums: dict[str, list[tuple[int, FileRef, str]]] = {}


def _actions_for(kinds: list[str]) -> list[str]:
    if len(kinds) == 1:
        return ACTIONS[kinds[0]]
    if len(set(kinds)) == 1:
        return MULTI_ACTIONS.get(kinds[0], MULTI_ACTIONS[ft.OTHER])
    return MULTI_ACTIONS[ft.OTHER]


async def offer_actions(message: Message, lang: str | None, refs: list[FileRef], kinds: list[str]) -> None:
    max_bytes = config.max_file_size_mb * 1024 * 1024
    too_big = [r for r in refs if r.file_size > max_bytes]
    if too_big:
        await message.reply(t(lang, "too_big", max_size=config.max_file_size_mb, size=ft.human_size(too_big[0].file_size)))
        kinds = [k for r, k in zip(refs, kinds) if r.file_size <= max_bytes]
        refs = [r for r in refs if r.file_size <= max_bytes]
        if not refs:
            return

    token = file_store.put(StoredFile(user_id=message.from_user.id, files=refs))
    if len(refs) == 1:
        text = t(
            lang,
            "file_received",
            name=escape(refs[0].file_name),
            size=ft.human_size(refs[0].file_size),
            kind=t(lang, f"kind_{kinds[0]}"),
        )
    else:
        text = t(lang, "files_received", n=len(refs), size=ft.human_size(sum(r.file_size for r in refs)))
    await message.reply(text, reply_markup=actions_keyboard(lang, _actions_for(kinds), token))


@router.message(F.document | F.photo)
async def on_file(message: Message, lang: str | None) -> None:
    ref, kind = ref_from_message(message)
    if message.media_group_id is None:
        await offer_actions(message, lang, [ref], [kind])
        return

    # Albom: har bir fayl alohida xabar bo'lib keladi — ularni yig'ib, bitta javob beramiz
    key = f"{message.chat.id}:{message.media_group_id}"
    batch = _albums.setdefault(key, [])
    batch.append((message.message_id, ref, kind))
    if len(batch) > 1:
        return

    await asyncio.sleep(ALBUM_WAIT_SECONDS)
    batch = sorted(_albums.pop(key), key=lambda x: x[0])
    await offer_actions(message, lang, [r for _, r, _ in batch], [k for _, _, k in batch])


@router.callback_query(ServiceCB.filter())
async def on_service(
    callback: CallbackQuery,
    callback_data: ServiceCB,
    state: FSMContext,
    bot: Bot,
    lang: str | None,
) -> None:
    item = file_store.get(callback_data.token, callback.from_user.id)

    if callback_data.service == CANCEL:
        file_store.pop(callback_data.token)
        await callback.answer()
        await callback.message.delete()
        return

    if item is None:
        await callback.answer(t(lang, "expired"), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    if callback_data.service in INTERACTIVE:
        file_store.pop(callback_data.token)
        await callback.answer()
        await INTERACTIVE[callback_data.service](callback, state, item, bot, lang)
        return

    if callback_data.service not in SERVICES:
        await callback.answer(t(lang, "coming_soon"), show_alert=True)
        return

    if item.busy:
        await callback.answer(t(lang, "busy"), show_alert=True)
        return

    item.busy = True
    await callback.answer()
    try:
        await run_service(bot, callback.message, item, callback_data.service, lang)
    finally:
        file_store.pop(callback_data.token)
