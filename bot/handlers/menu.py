"""«🛠 Xizmatlar» menyusi: avval xizmat tanlanadi, keyin fayl yuboriladi."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import config
from bot.handlers import collect, pdf_tools
from bot.locales import all_variants, t
from bot.services import SERVICE_KINDS
from bot.services.runner import run_service
from bot.states import ServiceStates
from bot.utils.file_store import StoredFile, ref_from_message
from bot.utils.filetypes import human_size

router = Router(name="menu")

CANCEL = "cancel"

MENU_ORDER = [
    "pdf_to_word", "pdf_to_images",
    "pdf_compress", "pdf_merge",
    "pdf_split", "word_to_pdf",
    "ppt_to_pdf", "excel_to_pdf",
    "images_to_pdf", "image_compress",
    "zip", "unzip",
]


class PickCB(CallbackData, prefix="pick"):
    service: str


def services_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for service in MENU_ORDER:
        kb.button(text=t(lang, f"menu_{service}"), callback_data=PickCB(service=service))
    kb.adjust(2)
    return kb.as_markup()


def _cancel_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=PickCB(service=CANCEL))
    return kb.as_markup()


@router.message(F.text.in_(all_variants("btn_services")))
async def cmd_services(message: Message, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await message.answer(t(lang, "services"), reply_markup=services_keyboard(lang))


@router.callback_query(PickCB.filter())
async def on_pick(callback: CallbackQuery, callback_data: PickCB, state: FSMContext, bot: Bot, lang: str | None) -> None:
    service = callback_data.service
    await callback.answer()

    if service == CANCEL:
        await state.clear()
        await callback.message.edit_text(t(lang, "cancelled"))
        return

    # bir nechta fayl yig'iladigan xizmatlar — darhol yig'ish rejimiga o'tamiz
    if service in collect.COLLECTORS:
        await collect.start_collect(service, callback, state, StoredFile(callback.from_user.id, []), bot, lang)
        return

    await state.set_state(ServiceStates.waiting_file)
    await state.set_data({"service": service})
    await callback.message.edit_text(
        t(lang, "send_file_for", title=t(lang, f"menu_{service}"), what=t(lang, f"need_{SERVICE_KINDS[service]}")),
        reply_markup=_cancel_keyboard(lang),
    )


@router.message(ServiceStates.waiting_file, F.document | F.photo)
async def on_service_file(message: Message, state: FSMContext, bot: Bot, lang: str | None) -> None:
    service = (await state.get_data())["service"]
    expected = SERVICE_KINDS[service]
    ref, kind = ref_from_message(message)

    if kind != expected:
        await message.reply(t(lang, "wrong_kind", what=t(lang, f"need_{expected}")))
        return
    if ref.file_size > config.max_file_size_mb * 1024 * 1024:
        await message.reply(t(lang, "too_big", max_size=config.max_file_size_mb, size=human_size(ref.file_size)))
        return

    status = await message.reply(t(lang, "processing", name=escape(ref.file_name)))
    if service == "pdf_split":
        await pdf_tools.begin_split(status, state, ref, bot, lang)
        return
    # holat saqlanib qoladi — foydalanuvchi shu xizmat uchun yana fayl yuborishi mumkin
    await run_service(bot, status, StoredFile(message.from_user.id, [ref]), service, lang)


@router.message(ServiceStates.waiting_file)
async def on_service_wrong_input(message: Message, state: FSMContext, lang: str | None) -> None:
    service = (await state.get_data())["service"]
    await message.reply(t(lang, "wrong_kind", what=t(lang, f"need_{SERVICE_KINDS[service]}")))
