from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.database import db
from bot.keyboards.common import lang_keyboard, main_menu
from bot.locales import LANGUAGES, all_variants, t
from bot.middlewares.subscription import SUB_CHECK

router = Router(name="start")


async def send_welcome(message: Message, lang: str, name: str) -> None:
    await message.answer(t(lang, "welcome", name=escape(name)), reply_markup=main_menu(lang))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    if not lang:
        await message.answer(t(None, "choose_lang"), reply_markup=lang_keyboard())
        return
    await send_welcome(message, lang, message.from_user.full_name)


@router.message(Command("lang"))
@router.message(F.text.in_(all_variants("btn_lang")))
async def cmd_lang(message: Message, lang: str | None) -> None:
    await message.answer(t(lang, "choose_lang"), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_chosen(callback: CallbackQuery, lang: str | None) -> None:
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in LANGUAGES:
        await callback.answer()
        return

    first_time = lang is None
    await db.set_lang(callback.from_user.id, new_lang)
    await callback.message.edit_text(t(new_lang, "lang_set"))
    await callback.answer()

    if first_time:
        await send_welcome(callback.message, new_lang, callback.from_user.full_name)
    else:
        await callback.message.answer(t(new_lang, "send_file"), reply_markup=main_menu(new_lang))


@router.message(Command("help"))
@router.message(F.text.in_(all_variants("btn_help")))
async def cmd_help(message: Message, lang: str | None) -> None:
    await message.answer(t(lang, "help", max_size=config.max_file_size_mb))


@router.callback_query(F.data == SUB_CHECK)
async def on_sub_checked(callback: CallbackQuery, lang: str | None) -> None:
    # bu yerga faqat obuna tasdiqlangandan keyin yetib keladi (SubscriptionMiddleware)
    await callback.answer(t(lang, "sub_ok"))
    await callback.message.delete()
    if not lang:
        await callback.message.answer(t(None, "choose_lang"), reply_markup=lang_keyboard())
        return
    await send_welcome(callback.message, lang, callback.from_user.full_name)
