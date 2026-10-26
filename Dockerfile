FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Tashkent

# LibreOffice (Word/Excel/PowerPoint → PDF) va shriftlar:
#   liberation — Times New Roman / Arial / Courier o'rnini bosadi (o'lchamlari bir xil)
#   carlito, caladea — Calibri va Cambria o'rnini bosadi
#   dejavu, noto — kirill va boshqa belgilar uchun
# libglib2.0-0 — pdf2docx ishlatadigan opencv uchun
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-calc libreoffice-impress \
        fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea \
        fonts-dejavu-core fonts-noto-core \
        libglib2.0-0 tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# root huquqisiz ishlaydi; data/ logs/ temp/ shu foydalanuvchiga tegishli
RUN useradd --create-home --uid 1000 bot \
    && mkdir -p data logs temp \
    && chown -R bot:bot /app
USER bot

CMD ["python", "main.py"]
