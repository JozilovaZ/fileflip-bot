"""Rasm xizmatlari: rasmlardan PDF, rasmni siqish va o'lchamini o'zgartirish."""
import asyncio
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from bot.services import ServiceError, register

# A4 o'lchami (pt) va chetdagi bo'sh joy
A4_WIDTH, A4_HEIGHT = 595, 842
PAGE_MARGIN = 20
# PDF ichidagi rasmlarning eng katta tomoni (px)
PDF_IMAGE_MAX_SIDE = 2480
# Shundan kichik oddiy JPEG lar PDF ga qayta siqilmasdan qo'yiladi (Telegram suratlari 2560px gacha)
PASSTHROUGH_MAX_SIDE = 2560
# EXIF dagi "burilmagan" holat
ORIENTATION_TAG, ORIENTATION_NORMAL = 0x0112, 1
COMPRESS_MAX_SIDE = 2560
JPEG_QUALITY = 70


def _open_image(src: Path, draft_side: int | None = None) -> Image.Image:
    try:
        img = Image.open(src)
        if draft_side:
            # katta JPEG ni to'liq o'lchamda ochmasdan, darhol kichraytirib o'qiydi — ancha tez
            img.draft("RGB", (draft_side, draft_side))
        img.load()
    except Exception:
        raise ServiceError("image_broken")
    # telefon rasmlari ko'pincha EXIF orqali buriladi — haqiqiy holatiga keltiramiz
    return ImageOps.exif_transpose(img)


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def _to_rgb(img: Image.Image) -> Image.Image:
    if _has_alpha(img):
        background = Image.new("RGB", img.size, "white")
        background.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        return background
    return img.convert("RGB")


def _shrink(img: Image.Image, max_side: int) -> Image.Image:
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return img


# --- Rasmlar → PDF ---

def _jpeg_passthrough(src: Path) -> tuple[bytes, int, int] | None:
    """Rasm qayta ishlashni talab qilmaydigan JPEG bo'lsa, uning baytlari va o'lchamini qaytaradi."""
    try:
        with Image.open(src) as img:
            if (
                img.format != "JPEG"
                or img.mode not in ("RGB", "L")
                or max(img.size) > PASSTHROUGH_MAX_SIDE
                or img.getexif().get(ORIENTATION_TAG, ORIENTATION_NORMAL) != ORIENTATION_NORMAL
            ):
                return None
            width, height = img.size
    except Exception:
        return None
    return src.read_bytes(), width, height


def _prepare_for_pdf(src: Path) -> tuple[bytes, int, int]:
    passthrough = _jpeg_passthrough(src)
    if passthrough:
        return passthrough
    img = _shrink(_to_rgb(_open_image(src, draft_side=PDF_IMAGE_MAX_SIDE)), PDF_IMAGE_MAX_SIDE)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue(), img.width, img.height


def _images_to_pdf(srcs: list[Path], out_dir: Path) -> list[Path]:
    result = out_dir / f"{srcs[0].stem}.pdf"
    with pymupdf.open() as doc:
        for src in srcs:
            data, img_width, img_height = _prepare_for_pdf(src)

            # yotiq rasm — yotiq sahifa
            landscape = img_width > img_height
            width, height = (A4_HEIGHT, A4_WIDTH) if landscape else (A4_WIDTH, A4_HEIGHT)
            page = doc.new_page(width=width, height=height)
            area = pymupdf.Rect(PAGE_MARGIN, PAGE_MARGIN, width - PAGE_MARGIN, height - PAGE_MARGIN)
            page.insert_image(area, stream=data, keep_proportion=True)
        doc.save(result, garbage=3, deflate=True)
    return [result]


async def images_to_pdf(srcs: list[Path], out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_images_to_pdf, srcs, out_dir)


# --- Rasmni siqish ---

def _compress(src: Path, out_dir: Path) -> list[Path]:
    img = _shrink(_open_image(src), COMPRESS_MAX_SIDE)
    if _has_alpha(img):
        # shaffof rasmlar PNG bo'lib qoladi, ranglar soni kamaytiriladi
        result = out_dir / f"{src.stem}_compressed.png"
        img.convert("RGBA").quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(result, "PNG", optimize=True)
    else:
        result = out_dir / f"{src.stem}_compressed.jpg"
        img.convert("RGB").save(result, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)

    if result.stat().st_size >= src.stat().st_size * 0.95:
        raise ServiceError("already_compressed")
    return [result]


@register("image_compress")
async def image_compress(src: Path, out_dir: Path) -> list[Path]:
    return await asyncio.to_thread(_compress, src, out_dir)


# --- O'lchamini o'zgartirish ---

RESIZE_MAX_SIDE = 8000
# Natija rasmining eng ko'p piksellari soni (xotirani himoya qilish uchun)
RESIZE_MAX_PIXELS = 40_000_000
RESIZE_JPEG_QUALITY = 92
# Aniq o'lchamga kesishda markaz biroz yuqoriroq — portretlarda bosh kesilib qolmasligi uchun
RESIZE_CENTERING = (0.5, 0.4)


@dataclass(frozen=True)
class ResizeSpec:
    width: int | None = None  # faqat eni berilsa — bo'yi proporsional
    height: int | None = None  # eni ham, bo'yi ham berilsa — aniq o'lcham (ortiqchasi kesiladi)
    percent: int | None = None
    dpi: int | None = None


# 3x4 sm hujjat rasmi, 300 DPI
DOC_3X4 = ResizeSpec(width=354, height=472, dpi=300)

_SIZE_RE = re.compile(r"(\d+)\s*[x×*хХ]\s*(\d+)", re.IGNORECASE)


def parse_size(text: str) -> ResizeSpec:
    """`800x600`, `1280` yoki `50%` ko'rinishidagi matnni o'qiydi. Xato bo'lsa — ValueError."""
    text = text.strip()
    if m := re.fullmatch(r"(\d+)\s*%", text):
        percent = int(m.group(1))
        if not 1 <= percent <= 400:
            raise ValueError(text)
        return ResizeSpec(percent=percent)
    if m := _SIZE_RE.fullmatch(text):
        width, height = int(m.group(1)), int(m.group(2))
    elif text.isdigit():
        width, height = int(text), None
    else:
        raise ValueError(text)
    if not all(1 <= side <= RESIZE_MAX_SIDE for side in (width, height) if side is not None):
        raise ValueError(text)
    return ResizeSpec(width=width, height=height)


def image_size(src: Path) -> tuple[int, int]:
    """Rasmning haqiqiy (EXIF burilishini hisobga olgan) o'lchami."""
    try:
        with Image.open(src) as img:
            width, height = img.size
            orientation = img.getexif().get(ORIENTATION_TAG, ORIENTATION_NORMAL)
    except Exception:
        raise ServiceError("image_broken")
    # 5–8 — rasm 90° burilgan, eni va bo'yi almashadi
    return (height, width) if orientation in (5, 6, 7, 8) else (width, height)


def _target_size(spec: ResizeSpec, width: int, height: int) -> tuple[int, int]:
    if spec.percent:
        return max(1, round(width * spec.percent / 100)), max(1, round(height * spec.percent / 100))
    if spec.height:
        return spec.width, spec.height
    return spec.width, max(1, round(height * spec.width / width))


def _resize(src: Path, out_dir: Path, spec: ResizeSpec) -> list[Path]:
    img = _open_image(src)
    width, height = _target_size(spec, *img.size)
    if width * height > RESIZE_MAX_PIXELS or max(width, height) > RESIZE_MAX_SIDE:
        raise ServiceError("resize_too_big", max=RESIZE_MAX_SIDE)

    if spec.width and spec.height:
        img = ImageOps.fit(img, (width, height), Image.LANCZOS, centering=RESIZE_CENTERING)
    else:
        img = img.resize((width, height), Image.LANCZOS)

    extra = {"dpi": (spec.dpi, spec.dpi)} if spec.dpi else {}
    if _has_alpha(img):
        result = out_dir / f"{src.stem}_{width}x{height}.png"
        img.convert("RGBA").save(result, "PNG", optimize=True, **extra)
    else:
        result = out_dir / f"{src.stem}_{width}x{height}.jpg"
        img.convert("RGB").save(result, "JPEG", quality=RESIZE_JPEG_QUALITY, optimize=True, **extra)
    return [result]


async def resize(src: Path, out_dir: Path, spec: ResizeSpec) -> list[Path]:
    return await asyncio.to_thread(_resize, src, out_dir, spec)
