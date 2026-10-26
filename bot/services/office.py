"""Word, PowerPoint va Excel fayllarni LibreOffice orqali PDF ga aylantirish."""
import asyncio
import logging
from pathlib import Path

from bot.config import config
from bot.services import ServiceError, register

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 180
# Bir vaqtda ishlaydigan LibreOffice nusxalari soni.
# Har bir nusxa o'z profil papkasidan foydalanadi, aks holda ular bir-biriga xalaqit beradi.
MAX_WORKERS = 2

_slots: asyncio.Queue[int] | None = None


def _get_slots() -> asyncio.Queue[int]:
    global _slots
    if _slots is None:
        _slots = asyncio.Queue()
        for i in range(MAX_WORKERS):
            _slots.put_nowait(i)
    return _slots


async def convert_to_pdf(src: Path, out_dir: Path) -> list[Path]:
    if not config.libreoffice_path:
        logger.error("LibreOffice topilmadi. .env faylida LIBREOFFICE_PATH ni ko'rsating")
        raise ServiceError("convert_failed")

    slots = _get_slots()
    slot = await slots.get()
    try:
        profile = (config.data_dir / f"lo_profile_{slot}").resolve()
        process = await asyncio.create_subprocess_exec(
            config.libreoffice_path,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--nologo",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
            str(src),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ServiceError("timeout")
    finally:
        slots.put_nowait(slot)

    result = out_dir / f"{src.stem}.pdf"
    if not result.is_file():
        logger.warning(
            "LibreOffice PDF yaratmadi: %s (kod=%s) %s",
            src.name, process.returncode, stderr.decode(errors="ignore").strip(),
        )
        raise ServiceError("convert_failed")
    return [result]


register("word_to_pdf")(convert_to_pdf)
register("ppt_to_pdf")(convert_to_pdf)
register("excel_to_pdf")(convert_to_pdf)
