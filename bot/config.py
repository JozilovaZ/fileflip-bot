import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _parse_ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


def _find_libreoffice() -> str | None:
    custom = os.getenv("LIBREOFFICE_PATH", "").strip()
    candidates = [
        custom,
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
    ]
    return next((c for c in candidates if c and Path(c).is_file()), None)


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    max_file_size_mb: int
    data_dir: Path
    temp_dir: Path
    db_path: Path
    libreoffice_path: str | None


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")

    data_dir = BASE_DIR / "data"
    temp_dir = BASE_DIR / "temp"
    data_dir.mkdir(exist_ok=True)
    temp_dir.mkdir(exist_ok=True)

    return Config(
        bot_token=token,
        admin_ids=_parse_ids(os.getenv("ADMIN_IDS", "")),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
        data_dir=data_dir,
        temp_dir=temp_dir,
        db_path=data_dir / "fileflip.db",
        libreoffice_path=_find_libreoffice(),
    )


config = load_config()
