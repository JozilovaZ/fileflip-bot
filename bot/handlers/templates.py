"""«📝 Hujjat shablonlari»: savollarga javob berib, tayyor ariza yoki tushuntirish xatini olish."""
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import all_variants, t
from bot.services import templates
from bot.services.runner import execute
from bot.states import TemplateStates

router = Router(name="templates")

CANCEL = "cancel"
FORMATS = ("docx", "pdf")


class TplCB(CallbackData, prefix="tpl"):
    action: str  # pick | docx | pdf | cancel
    key: str = ""


def _cancel_button(kb: InlineKeyboardBuilder, lang: str | None) -> None:
    kb.button(text=t(lang, "btn_cancel"), callback_data=TplCB(action=CANCEL))


def _templates_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in templates.TEMPLATES:
        kb.button(text=t(lang, f"tpl_name_{key}"), callback_data=TplCB(action="pick", key=key))
    _cancel_button(kb, lang)
    kb.adjust(1)
    return kb.as_markup()


def _cancel_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _cancel_button(kb, lang)
    return kb.as_markup()


def _format_keyboard(lang: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for fmt in FORMATS:
        kb.button(text=t(lang, f"btn_tpl_{fmt}"), callback_data=TplCB(action=fmt))
    _cancel_button(kb, lang)
    kb.adjust(2, 1)
    return kb.as_markup()


def _question(lang: str | None, key: str, step: int) -> str:
    fields = templates.TEMPLATES[key].fields
    return t(
        lang, "tpl_ask",
        title=t(lang, f"tpl_name_{key}"), step=step + 1, total=len(fields),
        question=t(lang, f"tpl_field_{fields[step]}"),
    )


@router.message(Command("templates"))
@router.message(F.text.in_(all_variants("btn_templates")))
async def cmd_templates(message: Message, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await message.answer(t(lang, "tpl_choose"), reply_markup=_templates_keyboard(lang))


@router.callback_query(TplCB.filter(F.action == CANCEL))
async def tpl_cancel(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(t(lang, "cancelled"))


@router.callback_query(TplCB.filter(F.action == "pick"))
async def tpl_pick(callback: CallbackQuery, callback_data: TplCB, state: FSMContext, lang: str | None) -> None:
    await callback.answer()
    if callback_data.key not in templates.TEMPLATES:
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    await state.set_state(TemplateStates.filling)
    await state.set_data({"key": callback_data.key, "answers": {}})
    await callback.message.edit_text(_question(lang, callback_data.key, 0), reply_markup=_cancel_keyboard(lang))


@router.message(TemplateStates.filling, F.text)
async def tpl_answer(message: Message, state: FSMContext, lang: str | None) -> None:
    data = await state.get_data()
    key, answers = data["key"], data["answers"]
    fields = templates.TEMPLATES[key].fields
    field = fields[len(answers)]
    try:
        answers[field] = templates.validate(field, message.text)
    except ValueError as e:
        rule = templates.FIELDS[field]
        await message.reply(t(lang, str(e), min=rule.min_len, max=rule.max_len, days=templates.MAX_DAYS))
        return

    await state.update_data(answers=answers)
    if len(answers) < len(fields):
        await message.answer(_question(lang, key, len(answers)), reply_markup=_cancel_keyboard(lang))
        return
    await state.set_state(TemplateStates.format)
    await message.answer(t(lang, "tpl_format"), reply_markup=_format_keyboard(lang))


@router.message(TemplateStates.filling)
async def tpl_wrong_input(message: Message, state: FSMContext, lang: str | None) -> None:
    data = await state.get_data()
    await message.reply(_question(lang, data["key"], len(data["answers"])), reply_markup=_cancel_keyboard(lang))


@router.message(TemplateStates.format)
async def tpl_format_wrong_input(message: Message, lang: str | None) -> None:
    await message.reply(t(lang, "tpl_format"), reply_markup=_format_keyboard(lang))


@router.callback_query(TplCB.filter(F.action.in_(FORMATS)), TemplateStates.format)
async def tpl_render(callback: CallbackQuery, callback_data: TplCB, state: FSMContext, bot: Bot, lang: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()

    async def work(srcs: list[Path], out_dir: Path) -> list[Path]:
        return await templates.render(data["key"], data["answers"], out_dir, callback_data.action)

    await execute(
        bot, callback.message, callback.from_user.id, "doc_template", lang, [], work,
        label=t(lang, f"tpl_name_{data['key']}"),
    )


@router.callback_query(TplCB.filter())
async def stale_button(callback: CallbackQuery, lang: str | None) -> None:
    await callback.answer(t(lang, "tpl_expired"), show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
