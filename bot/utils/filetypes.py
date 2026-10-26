from pathlib import Path

PDF = "pdf"
WORD = "word"
PPT = "ppt"
EXCEL = "excel"
IMAGE = "image"
ZIP = "zip"
OTHER = "other"

_BY_EXTENSION = {
    ".pdf": PDF,
    ".doc": WORD, ".docx": WORD, ".odt": WORD, ".rtf": WORD,
    ".ppt": PPT, ".pptx": PPT, ".odp": PPT,
    ".xls": EXCEL, ".xlsx": EXCEL, ".ods": EXCEL, ".csv": EXCEL,
    ".jpg": IMAGE, ".jpeg": IMAGE, ".png": IMAGE, ".webp": IMAGE, ".bmp": IMAGE,
    ".tif": IMAGE, ".tiff": IMAGE,
    ".zip": ZIP,
}

_BY_MIME = {
    "application/pdf": PDF,
    "application/msword": WORD,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": WORD,
    "application/vnd.ms-powerpoint": PPT,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": PPT,
    "application/vnd.ms-excel": EXCEL,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": EXCEL,
    "application/zip": ZIP,
    "application/x-zip-compressed": ZIP,
}

_INVALID_CHARS = '<>:"/\\|?*'


def detect_kind(file_name: str | None, mime_type: str | None) -> str:
    if file_name:
        kind = _BY_EXTENSION.get(Path(file_name).suffix.lower())
        if kind:
            return kind
    if mime_type:
        if mime_type.startswith("image/"):
            return IMAGE
        return _BY_MIME.get(mime_type, OTHER)
    return OTHER


def safe_filename(name: str | None, default: str = "file") -> str:
    """Fayl nomidan xavfli belgilarni olib tashlaydi."""
    name = Path(name or "").name.strip()
    cleaned = "".join("_" if c in _INVALID_CHARS or ord(c) < 32 else c for c in name)
    cleaned = cleaned.strip(" .")
    return cleaned[:150] or default


def human_size(size: int | None) -> str:
    size = float(size or 0)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
