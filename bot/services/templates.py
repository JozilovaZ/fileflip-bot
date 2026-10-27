"""Hujjat shablonlari: foydalanuvchi javoblaridan ariza va tushuntirish xati yasash (Word yoki PDF)."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Cm, Pt

from bot.services.office import convert_to_pdf

# Hujjat sanasi O'zbekiston vaqtida
LOCAL_TZ = timezone(timedelta(hours=5))
FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(14)
# «Kimga / kimdan» bloki sahifaning o'ng yarmida turadi
HEADER_INDENT = Cm(9)
DATE_FORMATS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y")


@dataclass(frozen=True)
class Template:
    title: str  # hujjat sarlavhasi
    file_name: str
    fields: tuple[str, ...]  # foydalanuvchidan so'raladigan maydonlar (tartibi bilan)
    body: str  # {maydon} lar bilan asosiy matn


TEMPLATES: dict[str, Template] = {
    "application": Template("ARIZA", "Ariza", ("to", "from", "text"), "{text}"),
    "resignation": Template(
        "ARIZA", "Ariza_ishdan_bushash", ("to", "from", "date"),
        "Meni {date} yildan o'z xohishimga ko'ra egallab turgan lavozimimdan ozod qilishingizni so'rayman.",
    ),
    "vacation": Template(
        "ARIZA", "Ariza_tatil", ("to", "from", "date", "days"),
        "Menga {date} yildan boshlab {days} kalendar kunlik navbatdagi mehnat ta'tilini berishingizni so'rayman.",
    ),
    "explanation": Template("TUSHUNTIRISH XATI", "Tushuntirish_xati", ("to", "from", "text"), "{text}"),
}


@dataclass(frozen=True)
class Field:
    min_len: int
    max_len: int


FIELDS: dict[str, Field] = {
    "to": Field(5, 300),
    "from": Field(5, 300),
    "text": Field(10, 3000),
    "date": Field(6, 10),
    "days": Field(1, 3),
}
MAX_DAYS = 365


def validate(field: str, text: str) -> str:
    """Javobni tekshiradi va saqlanadigan ko'rinishga keltiradi.

    Xato bo'lsa — ValueError, uning matni locales dagi xato kaliti.
    """
    text = text.strip()
    rule = FIELDS[field]
    if len(text) < rule.min_len:
        raise ValueError("tpl_bad_short")
    if len(text) > rule.max_len:
        raise ValueError("tpl_bad_long")
    if field == "date":
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime("%d.%m.%Y")
            except ValueError:
                pass
        raise ValueError("tpl_bad_date")
    if field == "days":
        if not text.isdigit() or not 1 <= int(text) <= MAX_DAYS:
            raise ValueError("tpl_bad_days")
        return str(int(text))
    return text


def _paragraph(doc, text: str = "", *, bold: bool = False, align=None, indent=None, first_line=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    if align is not None:
        p.alignment = align
    if indent is not None:
        p.paragraph_format.left_indent = indent
    if first_line is not None:
        p.paragraph_format.first_line_indent = first_line
    if text:
        p.add_run(text).bold = bold
    return p


def _build_docx(template: Template, answers: dict[str, str], path: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.left_margin, section.right_margin = Cm(3), Cm(1.5)
    section.top_margin, section.bottom_margin = Cm(2), Cm(2)
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = FONT_SIZE
    # kirill va boshqa yozuvlar uchun ham shu shrift
    style.element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", FONT_NAME)

    to = _paragraph(doc, answers["to"], indent=HEADER_INDENT)
    to.paragraph_format.space_after = Pt(8)
    _paragraph(doc, answers["from"], indent=HEADER_INDENT)
    for _ in range(2):
        _paragraph(doc)
    _paragraph(doc, template.title, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _paragraph(doc)

    for line in template.body.format(**answers).splitlines():
        p = _paragraph(doc, line.strip(), align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_line=Cm(1.25))
        p.paragraph_format.line_spacing = 1.5

    for _ in range(2):
        _paragraph(doc)
    # sana chapda, imzo o'ng chetda
    footer = _paragraph(doc)
    width = section.page_width - section.left_margin - section.right_margin
    footer.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)
    footer.add_run(f"{datetime.now(LOCAL_TZ):%d.%m.%Y}-yil\t____________ (imzo)")
    doc.save(path)


async def render(key: str, answers: dict[str, str], out_dir: Path, fmt: str) -> list[Path]:
    """Shablondan hujjat yasaydi. `fmt` — docx yoki pdf."""
    template = TEMPLATES[key]
    path = out_dir / f"{template.file_name}_{datetime.now(LOCAL_TZ):%d.%m.%Y}.docx"
    await asyncio.to_thread(_build_docx, template, answers, path)
    if fmt == "pdf":
        return await convert_to_pdf(path, out_dir)
    return [path]
