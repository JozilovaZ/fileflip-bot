# Fayl konvertor bot — ish rejasi

Texnologiyalar: Python 3.11, aiogram 3, SQLite (aiosqlite), LibreOffice, pdf2docx, PyMuPDF, Pillow.
Fayl hajmi chegarasi: 20 MB (Telegram Bot API cheklovi).

## 1-bosqich. Poydevor
- [x] Loyiha tuzilmasi (`bot/handlers`, `bot/keyboards`, `bot/locales`, `bot/database`, `bot/middlewares`, `bot/utils`)
- [x] `requirements.txt`, `.env` (BOT_TOKEN, ADMIN_IDS), `config.py`
- [x] `/start`, til tanlash (o'zbek, rus, ingliz), asosiy menyu
- [x] SQLite: `users` va `stats` jadvallari
- [x] Vaqtinchalik fayllar papkasi va avtomatik tozalash

## 2-bosqich. Aqlli fayl qabul qilish
- [x] Fayl turini aniqlash (pdf, docx, pptx, xlsx, rasm, zip)
- [x] Turiga mos tugmalarni chiqarish
- [x] 20 MB chegarasini tekshirish, "⏳ Jarayonda..." xabari
- [x] Xatolarni ushlash va foydalanuvchiga tushunarli xabar berish
- [x] «Xizmatlar» menyusi: avval xizmat tanlanadi, keyin fayl yuboriladi (qo'shimcha)

## 3-bosqich. Office → PDF (LibreOffice)
- [x] Word → PDF
- [x] PPTX → PDF
- [x] Excel → PDF

## 4-bosqich. PDF xizmatlari
- [x] PDF → Word (pdf2docx)
- [x] PDF → rasmlar (PyMuPDF)
- [x] PDF siqish
- [x] PDF birlashtirish (bir nechta fayl → "Tayyor" tugmasi)
- [x] PDF ajratish (sahifa oralig'i: `1-3, 5`)

## 5-bosqich. Rasm xizmatlari
- [x] Bir nechta rasm → bitta PDF
- [x] Rasmni siqish
- [x] Albom qo'llab-quvvatlash: bir nechta fayl — bitta javob (qo'shimcha)

## 6-bosqich. Arxiv
- [x] Bitta yoki bir nechta faylni ZIP qilish
- [x] ZIPni ochish (fayllarni alohida yuborish)

## 7-bosqich. Admin panel
- [x] `/admin`: statistika (foydalanuvchilar, xizmatlar bo'yicha)
- [x] Hammaga xabar yuborish (rassilka)
- [x] Majburiy obuna (yoqish/o'chirish)

## 8-bosqich. Himoya va sayqal
- [x] Spamga qarshi cheklov (throttling)
- [x] Bir vaqtda bajariladigan konvertatsiyalar sonini cheklash (navbat)
- [x] Loglar (bosqichlar vaqti bilan: yuklash / ish / yuborish)
- [x] README: o'rnatish va ishga tushirish
- [x] «📂 Mening fayllarim» — natijalar tarixi (qo'shimcha)
- [x] Docker: `Dockerfile`, `docker-compose.yml` (polling, nginx'siz)
- [ ] Serverga joylash va u yerda sinash
