# FileFlip — Telegram fayl konvertor bot

[@File_UzFlip_bot](https://t.me/File_UzFlip_bot): PDF, Word, PowerPoint, Excel, rasm va ZIP fayllarni aylantiruvchi bot.

**Xizmatlar:** PDF ↔ Word, PDF → rasmlar, PDF siqish, birlashtirish va ajratish, Office → PDF, rasmlar → PDF, rasm siqish va o'lchamini o'zgartirish, ZIP qilish va ochish.
Bot uch tilda ishlaydi (o'zbek, rus, ingliz). Admin panel, majburiy obuna va "Mening fayllarim" tarixi bor.

**Texnologiyalar:** Python 3.11, aiogram 3, SQLite, LibreOffice, PyMuPDF, pdf2docx, Pillow.

---

## Sozlamalar (`.env`)

`.env.example` faylidan nusxa olib, `.env` nomi bilan saqlang:

| O'zgaruvchi | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `ADMIN_IDS` | Adminlarning Telegram ID lari, vergul bilan: `111,222` |
| `MAX_FILE_SIZE_MB` | Qabul qilinadigan eng katta fayl (Telegram cheklovi: 20) |
| `LIBREOFFICE_PATH` | Bo'sh qoldiring: bot o'zi topadi. Faqat nostandart joyga o'rnatilgan bo'lsa ko'rsating |

> ⚠️ `.env` faylini hech kimga yubormang va GitHub'ga yuklamang.

---

## Serverga o'rnatish (Docker)

Ubuntu 22.04/24.04 VPS uchun. Tavsiya etiladigan server: **kamida 2 GB RAM, 2 CPU, 20 GB disk**.

### 1. Docker o'rnatish

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # keyin serverdan chiqib, qayta kiring
```

### 2. Loyihani serverga ko'chirish

Git orqali:
```bash
git clone <repo-manzili> fileflip && cd fileflip
```

Yoki o'z kompyuteringizdan (PowerShell):
```powershell
scp -r D:\topshiriqlar\pdf_bot user@SERVER_IP:~/fileflip
```
`.venv`, `data`, `temp` papkalarini ko'chirish shart emas.

### 3. Sozlash va ishga tushirish

```bash
cd ~/fileflip
cp .env.example .env
nano .env                                  # BOT_TOKEN va ADMIN_IDS ni yozing

docker compose up -d --build
```

Birinchi yig'ish 5–10 daqiqa davom etadi, chunki LibreOffice o'rnatiladi.

### 4. Tekshirish

```bash
docker compose ps            # holati: running
docker compose logs -f       # jonli loglar (chiqish: Ctrl+C)
```

Logda `Run polling for bot @File_UzFlip_bot` chiqsa, bot ishga tushgan.

> ⚠️ Bitta token bilan bot faqat **bitta joyda** ishlashi mumkin. Serverda ishga tushirishdan oldin
> kompyuteringizdagi botni to'xtating, aks holda `Conflict: terminated by other getUpdates request` xatosi chiqadi.

---

## Boshqaruv

| Vazifa | Buyruq |
|---|---|
| Loglar | `docker compose logs -f --tail 100` |
| Xizmatlar logi (fayl) | `tail -f logs/bot.log` |
| Qayta ishga tushirish | `docker compose restart` |
| To'xtatish | `docker compose down` |
| Kodni yangilash | `git pull && docker compose up -d --build` |

Server qayta yuklansa, bot avtomatik ishga tushadi (`restart: unless-stopped`).

### Zaxira nusxa

Barcha ma'lumotlar (foydalanuvchilar, statistika, tarix, sozlamalar) `data/fileflip.db` faylida saqlanadi:

```bash
cp data/fileflip.db ~/fileflip-backup-$(date +%F).db
```

---

## Lokal ishga tushirish (Windows)

1. Python 3.11 va [LibreOffice](https://www.libreoffice.org/download/) o'rnating.
2. Kutubxonalarni o'rnating va botni ishga tushiring:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # keyin .env ni to'ldiring
python main.py
```

---

## Loyiha tuzilmasi

```
main.py                 kirish nuqtasi: logging, middleware'lar, polling
bot/
  config.py             .env dan sozlamalar
  handlers/             xabar va tugmalarga javoblar (start, menu, files, history, admin...)
  services/             konvertatsiyalar: pdf, office, image, archive; runner — navbat va yuborish
  database/             SQLite: users, stats, history, settings
  middlewares/          foydalanuvchi, spamga qarshi cheklov, majburiy obuna
  locales/texts.py      uz / ru / en matnlar
  keyboards/, utils/
data/                   baza va LibreOffice profillari (zaxiralang)
logs/bot.log            xizmatlar logi (5 MB × 5 fayl)
temp/                   vaqtinchalik fayllar (avtomatik tozalanadi)
```

**Cheklovlar** (`bot/services/runner.py`): bir vaqtda 3 ta konvertatsiya bajariladi, bitta foydalanuvchining navbatida 5 tagacha ish turishi mumkin.
