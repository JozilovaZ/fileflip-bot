"""Arxiv xizmatlari: fayllarni ZIP qilish va ZIP ni ochish."""
import asyncio
import zipfile
from pathlib import Path, PurePosixPath

from bot.services import ServiceError, register
from bot.utils.archive import make_zip
from bot.utils.filetypes import safe_filename

MAX_UNZIP_FILES = 30
MAX_UNZIP_TOTAL_BYTES = 200 * 1024 * 1024
# Telegram bot 50 MB dan katta faylni yubora olmaydi
MAX_UNZIP_FILE_BYTES = 50 * 1024 * 1024
# Arxivlarda ko'p uchraydigan keraksiz fayllar
_JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
_UTF8_FLAG = 0x800


# --- ZIP qilish ---

def _zip_files(srcs: list[Path], out_dir: Path) -> list[Path]:
    name = f"{srcs[0].stem}.zip" if len(srcs) == 1 else "FileFlip.zip"
    return [make_zip(srcs, out_dir / name)]


async def zip_files(srcs: list[Path], out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_zip_files, srcs, out_dir)


# --- ZIP ni ochish ---

def _entry_name(info: zipfile.ZipInfo) -> str:
    """Fayl nomini to'g'ri kodlashda o'qiydi.

    UTF-8 belgisi bo'lmagan arxivlarda Python nomni cp437 deb o'qiydi, lekin
    Windows da yaratilgan arxivlar ko'pincha UTF-8 yoki cp866 (kirill) da bo'ladi.
    """
    name = info.filename
    if not info.flag_bits & _UTF8_FLAG:
        raw = name.encode("cp437", errors="ignore")
        for encoding in ("utf-8", "cp866"):
            try:
                name = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    return name


def _is_junk(name: str) -> bool:
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return any(p == "__MACOSX" for p in parts) or (parts and parts[-1].lower() in _JUNK_NAMES)


def _unique(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def _unzip(src: Path, out_dir: Path) -> list[Path]:
    try:
        zf = zipfile.ZipFile(src)
    except (zipfile.BadZipFile, OSError):
        raise ServiceError("zip_broken")

    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir() and not _is_junk(_entry_name(i))]
        if not entries:
            raise ServiceError("zip_empty")
        if len(entries) > MAX_UNZIP_FILES:
            raise ServiceError("zip_too_many", max=MAX_UNZIP_FILES)
        if any(i.flag_bits & 0x1 for i in entries):
            raise ServiceError("zip_encrypted")
        if sum(i.file_size for i in entries) > MAX_UNZIP_TOTAL_BYTES:
            raise ServiceError("zip_too_large")

        results: list[Path] = []
        total = 0
        for info in entries:
            # papkalar olib tashlanadi — faqat fayl nomi qoladi (xavfsiz yo'l)
            name = safe_filename(PurePosixPath(_entry_name(info).replace("\\", "/")).name)
            dest = _unique(out_dir / name)
            written = 0
            try:
                with zf.open(info) as source, open(dest, "wb") as target:
                    # arxivdagi o'lchamga ishonmaymiz — haqiqatda yozilganini sanaymiz
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        total += len(chunk)
                        if written > MAX_UNZIP_FILE_BYTES or total > MAX_UNZIP_TOTAL_BYTES:
                            raise ServiceError("zip_too_large")
                        target.write(chunk)
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError):
                raise ServiceError("zip_broken")
            results.append(dest)
    return results


@register("unzip")
async def unzip(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_unzip, src, out_dir)
