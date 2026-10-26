#!/bin/sh
# Serverdagi data/ va logs/ papkalari ko'pincha root nomidan yaratiladi.
# Konteyner root bo'lib ishga tushadi, papkalarni `bot` foydalanuvchisiga o'tkazadi
# va botni shu foydalanuvchi huquqlari bilan (root'siz) ishga tushiradi.
set -e
mkdir -p /app/data /app/logs /app/temp
chown -R bot:bot /app/data /app/logs /app/temp
# setpriv HOME ni o'zgartirmaydi — LibreOffice va fontconfig keshi uchun kerak
export HOME=/home/bot
exec setpriv --reuid=bot --regid=bot --init-groups "$@"
