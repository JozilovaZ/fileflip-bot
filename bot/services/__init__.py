"""Xizmatlar ro'yxati.

Har bir xizmat — `async def service(src: Path, out_dir: Path) -> list[Path]` ko'rinishidagi funksiya:
kirish faylini oladi va tayyor fayllar ro'yxatini qaytaradi.
Yangi xizmat `@register("kalit")` dekoratori bilan qo'shiladi.
"""
from pathlib import Path
from typing import Awaitable, Callable

from bot.utils import filetypes as ft

ServiceFunc = Callable[[Path, Path], Awaitable[list[Path]]]

SERVICES: dict[str, ServiceFunc] = {}

# Fayl turiga qarab ko'rsatiladigan tugmalar (tartibi bilan)
ACTIONS: dict[str, list[str]] = {
    ft.PDF: ["pdf_to_word", "pdf_to_images", "pdf_compress", "pdf_merge", "pdf_split", "zip"],
    ft.WORD: ["word_to_pdf", "zip"],
    ft.PPT: ["ppt_to_pdf", "zip"],
    ft.EXCEL: ["excel_to_pdf", "zip"],
    ft.IMAGE: ["images_to_pdf", "image_compress", "zip"],
    ft.ZIP: ["unzip"],
    ft.OTHER: ["zip"],
}

# Bir nechta fayl (albom) kelganda ko'rsatiladigan tugmalar
MULTI_ACTIONS: dict[str, list[str]] = {
    ft.PDF: ["pdf_merge", "zip"],
    ft.IMAGE: ["images_to_pdf", "zip"],
    ft.OTHER: ["zip"],
}

# Menyudan xizmat tanlanganda qabul qilinadigan fayl turi
# (zip — istalgan fayl, shuning uchun bu ro'yxatda yo'q)
SERVICE_KINDS: dict[str, str] = {
    "pdf_to_word": ft.PDF,
    "pdf_to_images": ft.PDF,
    "pdf_compress": ft.PDF,
    "pdf_merge": ft.PDF,
    "pdf_split": ft.PDF,
    "word_to_pdf": ft.WORD,
    "ppt_to_pdf": ft.PPT,
    "excel_to_pdf": ft.EXCEL,
    "images_to_pdf": ft.IMAGE,
    "image_compress": ft.IMAGE,
    "unzip": ft.ZIP,
}

# Natijada "eski hajm → yangi hajm" ko'rsatiladigan xizmatlar
COMPRESS_SERVICES = {"pdf_compress", "image_compress"}


class ServiceError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato. `key` — locales dagi matn kaliti."""

    def __init__(self, key: str = "error", **kwargs):
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


def register(key: str) -> Callable[[ServiceFunc], ServiceFunc]:
    def decorator(func: ServiceFunc) -> ServiceFunc:
        SERVICES[key] = func
        return func

    return decorator


# Xizmat modullarini yuklash: ular import paytida o'zlarini ro'yxatdan o'tkazadi
from bot.services import archive, image, office, pdf  # noqa: E402, F401
