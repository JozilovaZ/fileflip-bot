import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.config import BASE_DIR, config
from bot.database import db, settings
from bot.handlers import setup_routers
from bot.locales import LANGUAGES, t
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware
from bot.utils import tempfiles


def _commands(lang: str | None) -> list[BotCommand]:
    return [
        BotCommand(command=name, description=t(lang, f"cmd_{name}"))
        for name in ("start", "templates", "history", "lang", "help")
    ]


logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    for lang in LANGUAGES:
        await bot.set_my_commands(_commands(lang), language_code=lang)
    await bot.set_my_commands(_commands(None))

    # adminlar menyusida qo'shimcha admin buyruqlari
    admin_commands = _commands(None) + [
        BotCommand(command="admin", description="Admin panel"),
        BotCommand(command="user", description="Foydalanuvchini topish: /user ID yoki @username"),
        BotCommand(command="ban", description="Bloklash: /ban ID"),
        BotCommand(command="unban", description="Blokdan chiqarish: /unban ID"),
    ]
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramBadRequest:
            logger.warning("Admin %s botga hali /start bosmagan — /admin menyuga qo'shilmadi", admin_id)


def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    # logs/bot.log — 5 MB dan oshsa yangi faylga o'tadi, oxirgi 5 tasi saqlanadi
    file_handler = RotatingFileHandler(log_dir / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")

    # force=True: pdf2docx import paytida o'zining sozlamasini o'rnatib qo'yadi
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(), file_handler],
        force=True,
    )
    # pdf2docx har bir sahifa uchun log yozadi — ularni yashiramiz
    for handler in logging.getLogger().handlers:
        handler.addFilter(lambda record: "pdf2docx" not in record.pathname or record.levelno >= logging.WARNING)
    # aiogram har bir so'rovni logga yozadi — faylni to'ldirib yubormasligi uchun faqat ogohlantirishlar
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    if not config.libreoffice_path:
        logger.warning("LibreOffice topilmadi — Word/PowerPoint/Excel → PDF ishlamaydi")

    await db.init_db()
    await settings.load()
    tempfiles.clear_all()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(UserMiddleware())
    # tartib muhim: avval spam tekshiruvi, keyin obuna
    throttling = ThrottlingMiddleware()
    dp.message.outer_middleware(throttling)
    dp.callback_query.outer_middleware(throttling)
    subscription = SubscriptionMiddleware()
    dp.message.outer_middleware(subscription)
    dp.callback_query.outer_middleware(subscription)
    dp.include_router(setup_routers())

    await set_commands(bot)
    cleanup_task = asyncio.create_task(tempfiles.cleanup_loop())
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")
