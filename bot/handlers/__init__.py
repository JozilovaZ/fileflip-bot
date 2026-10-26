from aiogram import Router

from bot.handlers import admin, collect, errors, fallback, files, history, menu, pdf_tools, start


def setup_routers() -> Router:
    router = Router(name="root")
    router.include_router(errors.router)
    router.include_router(start.router)
    router.include_router(admin.router)
    # menyu tugmasi har qanday holatda (masalan, fayl kutilayotganda) ham ishlashi uchun oldinroq
    router.include_router(history.router)
    router.include_router(menu.router)
    # holatga bog'liq handlerlar oddiy fayl qabul qilishdan oldin turishi kerak
    router.include_router(collect.router)
    router.include_router(pdf_tools.router)
    router.include_router(files.router)
    # fallback har doim oxirida bo'lishi kerak
    router.include_router(fallback.router)
    return router
