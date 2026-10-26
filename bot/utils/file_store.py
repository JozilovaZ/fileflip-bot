import secrets
import time
from dataclasses import dataclass, field

from aiogram.types import Message

from bot.utils import filetypes as ft

TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class FileRef:
    file_id: str
    file_name: str
    file_size: int


@dataclass
class StoredFile:
    user_id: int
    files: list[FileRef]
    busy: bool = False
    created: float = field(default_factory=time.time)


_files: dict[str, StoredFile] = {}


def ref_from_message(message: Message) -> tuple[FileRef, str] | None:
    """Xabardagi fayl (hujjat yoki foto) va uning turini qaytaradi."""
    if message.document:
        doc = message.document
        name = ft.safe_filename(doc.file_name)
        return FileRef(doc.file_id, name, doc.file_size or 0), ft.detect_kind(name, doc.mime_type)
    if message.photo:
        photo = message.photo[-1]  # eng yuqori sifatli varianti
        return FileRef(photo.file_id, f"photo_{message.message_id}.jpg", photo.file_size or 0), ft.IMAGE
    return None


def _drop_expired() -> None:
    deadline = time.time() - TTL_SECONDS
    for token in [k for k, v in _files.items() if v.created < deadline]:
        del _files[token]


def put(item: StoredFile) -> str:
    """Faylni saqlab, tugmalar uchun qisqa token qaytaradi."""
    _drop_expired()
    token = secrets.token_hex(4)
    _files[token] = item
    return token


def get(token: str, user_id: int) -> StoredFile | None:
    item = _files.get(token)
    if item is None or item.user_id != user_id or time.time() - item.created > TTL_SECONDS:
        return None
    return item


def pop(token: str) -> None:
    _files.pop(token, None)
