"""PDF xizmatlari: Word ga, rasmlarga, siqish, birlashtirish, ajratish."""
import asyncio
import logging
import re
import warnings
from pathlib import Path

import pymupdf

from bot.services import ServiceError, register
from bot.utils.archive import make_zip

# pdf2docx eski `fitz` nomini import qiladi va ogohlantirish chiqaradi
warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")
from pdf2docx import Converter  # noqa: E402

logger = logging.getLogger(__name__)

MAX_PAGES = 300
MAX_WORD_PAGES = 100
IMAGE_DPI = 150
# Bundan ko'p fayl chiqsa, ular ZIP ga joylanadi
MAX_LOOSE_FILES = 10


def _open(src: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(src, filetype="pdf")
    except Exception:
        raise ServiceError("pdf_broken")
    if doc.needs_pass:
        doc.close()
        raise ServiceError("pdf_encrypted")
    if doc.page_count == 0:
        doc.close()
        raise ServiceError("pdf_broken")
    return doc


def _check_pages(doc: pymupdf.Document, limit: int = MAX_PAGES) -> None:
    if doc.page_count > limit:
        raise ServiceError("too_many_pages", max=limit)


def _bundle(files: list[Path], zip_path: Path) -> list[Path]:
    return [make_zip(files, zip_path)] if len(files) > MAX_LOOSE_FILES else files


def page_count(src: Path) -> int:
    with _open(src) as doc:
        return doc.page_count


def parse_pages(text: str, total: int) -> list[int]:
    """`1-3, 5` ko'rinishidagi matnni 0 dan boshlanuvchi sahifa raqamlariga aylantiradi."""
    text = re.sub(r"\s*[-–—]\s*", "-", text.strip())
    parts = [p for p in re.split(r"[,;\s]+", text) if p]
    if not parts:
        raise ValueError(text)

    pages: list[int] = []
    for part in parts:
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValueError(part)
        start = int(match[1])
        end = int(match[2] or start)
        if not 1 <= start <= end <= total:
            raise ValueError(part)
        pages.extend(range(start - 1, end))
    return pages


# --- PDF → Word ---

def _pdf_to_word(src: Path, out_dir: Path) -> list[Path]:
    with _open(src) as doc:
        _check_pages(doc, MAX_WORD_PAGES)
    result = out_dir / f"{src.stem}.docx"
    converter = Converter(str(src))
    try:
        converter.convert(str(result))
    finally:
        converter.close()
    return [result]


@register("pdf_to_word")
async def pdf_to_word(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_pdf_to_word, src, out_dir)


# --- PDF → rasmlar ---

def _pdf_to_images(src: Path, out_dir: Path) -> list[Path]:
    images: list[Path] = []
    with _open(src) as doc:
        _check_pages(doc)
        width = len(str(doc.page_count))
        for page in doc:
            path = out_dir / f"{src.stem}_{page.number + 1:0{width}d}.jpg"
            # pymupdf ning o'z JPEG saqlashi PIL dan ~25 marta sekin
            page.get_pixmap(dpi=IMAGE_DPI).pil_save(path, format="JPEG", quality=90)
            images.append(path)
    return _bundle(images, out_dir / f"{src.stem}_images.zip")


@register("pdf_to_images")
async def pdf_to_images(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_pdf_to_images, src, out_dir)


# --- PDF siqish ---

def _page_fingerprint(doc: pymupdf.Document) -> list[tuple[str, frozenset[str]]]:
    """Har bir sahifaning matni va joylangan (embedded) shriftlari."""
    return [
        (page.get_text(), frozenset(f[3] for f in page.get_fonts() if f[1] != "n/a"))
        for page in doc
    ]


def _compress(src: Path, out_dir: Path) -> list[Path]:
    result = out_dir / f"{src.stem}_compressed.pdf"
    with _open(src) as doc:
        _check_pages(doc)
        before = _page_fingerprint(doc)
        # Faqat rasmlar siqiladi. subset_fonts() va clean=True ishlatilmaydi:
        # ular Word PDF laridagi shriftlarni o'chirib, telefonda matnni buzib qo'yardi
        doc.rewrite_images(dpi_threshold=150, dpi_target=120, quality=70)
        doc.save(result, garbage=4, deflate=True, use_objstms=1)

    # siqilgan faylda matn yoki shriftlar o'zgargan bo'lsa — buzilgan faylni yubormaymiz
    with pymupdf.open(result) as compressed:
        if _page_fingerprint(compressed) != before:
            logger.warning("PDF siqishda matn/shrift o'zgardi, natija yuborilmadi: %s", src.name)
            raise ServiceError("already_compressed")

    if result.stat().st_size >= src.stat().st_size * 0.95:
        raise ServiceError("already_compressed")
    return [result]


@register("pdf_compress")
async def pdf_compress(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_compress, src, out_dir)


# --- Birlashtirish ---

def _merge(srcs: list[Path], out_dir: Path) -> list[Path]:
    result = out_dir / f"{srcs[0].stem}_merged.pdf"
    with pymupdf.open() as merged:
        for src in srcs:
            with _open(src) as doc:
                merged.insert_pdf(doc)
            _check_pages(merged)
        merged.save(result, garbage=3, deflate=True)
    return [result]


async def merge_pdfs(srcs: list[Path], out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_merge, srcs, out_dir)


# --- Ajratish ---

def _extract(src: Path, out_dir: Path, pages: list[int], label: str) -> list[Path]:
    result = out_dir / f"{src.stem}_{label}.pdf"
    with _open(src) as doc:
        doc.select(pages)
        doc.save(result, garbage=3, deflate=True)
    return [result]


async def extract_pages(src: Path, out_dir: Path, pages: list[int], label: str) -> list[Path]:
    return await asyncio.to_thread(_extract, src, out_dir, pages, label)


def _split_all(src: Path, out_dir: Path) -> list[Path]:
    files: list[Path] = []
    with _open(src) as doc:
        _check_pages(doc)
        width = len(str(doc.page_count))
        for i in range(doc.page_count):
            path = out_dir / f"{src.stem}_{i + 1:0{width}d}.pdf"
            with pymupdf.open() as single:
                single.insert_pdf(doc, from_page=i, to_page=i)
                single.save(path, garbage=3, deflate=True)
            files.append(path)
    return _bundle(files, out_dir / f"{src.stem}_pages.zip")


async def split_all(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_split_all, src, out_dir)
