from datetime import datetime, timedelta, timezone

import aiosqlite

from bot.config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    full_name   TEXT,
    username    TEXT,
    lang        TEXT,
    is_blocked  INTEGER NOT NULL DEFAULT 0,  -- foydalanuvchi botni bloklagan
    is_banned   INTEGER NOT NULL DEFAULT 0,  -- admin foydalanuvchini bloklagan
    created_at  TEXT NOT NULL,
    last_active TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    service    TEXT NOT NULL,
    success    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stats_service ON stats(service);
CREATE INDEX IF NOT EXISTS idx_stats_created ON stats(created_at);

-- foydalanuvchiga yuborilgan tayyor fayllar (Telegram file_id orqali qayta yuboriladi)
CREATE TABLE IF NOT EXISTS history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    service    TEXT NOT NULL,
    file_id    TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    file_size  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> aiosqlite.Connection:
    return aiosqlite.connect(config.db_path)


async def init_db() -> None:
    async with _connect() as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(SCHEMA)
        # eski bazalarda keyin qo'shilgan ustunlar yo'q bo'ladi
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if "is_banned" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
        await db.commit()


async def upsert_user(user_id: int, full_name: str, username: str | None) -> tuple[str | None, bool]:
    """Foydalanuvchini qo'shadi yoki yangilaydi va uning tilini hamda bloklanganligini qaytaradi."""
    now = _now()
    async with _connect() as db:
        await db.execute(
            """
            INSERT INTO users (user_id, full_name, username, created_at, last_active)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                username = excluded.username,
                is_blocked = 0,
                last_active = excluded.last_active
            """,
            (user_id, full_name, username, now, now),
        )
        await db.commit()
        async with db.execute("SELECT lang, is_banned FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return (row[0], bool(row[1])) if row else (None, False)


async def set_lang(user_id: int, lang: str) -> None:
    async with _connect() as db:
        await db.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()


async def log_service(user_id: int, service: str, success: bool = True) -> None:
    async with _connect() as db:
        await db.execute(
            "INSERT INTO stats (user_id, service, success, created_at) VALUES (?, ?, ?, ?)",
            (user_id, service, int(success), _now()),
        )
        await db.commit()


# Har bir foydalanuvchi uchun saqlanadigan natijalar soni
HISTORY_LIMIT = 20


async def add_history(user_id: int, service: str, files: list[tuple[str, str, int]]) -> None:
    """Tayyor fayllarni (file_id, nom, hajm) tarixga yozadi; eng eskilari o'chiriladi."""
    now = _now()
    async with _connect() as db:
        await db.executemany(
            "INSERT INTO history (user_id, service, file_id, file_name, file_size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(user_id, service, file_id, name, size, now) for file_id, name, size in files],
        )
        await db.execute(
            "DELETE FROM history WHERE user_id = ? AND id NOT IN "
            "(SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?)",
            (user_id, user_id, HISTORY_LIMIT),
        )
        await db.commit()


async def get_history(user_id: int) -> list[tuple[int, str, str, int, str]]:
    """(id, xizmat, nom, hajm, sana) — eng yangisi birinchi."""
    async with _connect() as db:
        async with db.execute(
            "SELECT id, service, file_name, file_size, created_at FROM history "
            "WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ) as cur:
            return list(await cur.fetchall())


async def get_history_file_id(user_id: int, item_id: int) -> str | None:
    """Faylning file_id si — faqat shu foydalanuvchining o'z fayli bo'lsa."""
    async with _connect() as db:
        async with db.execute(
            "SELECT file_id FROM history WHERE id = ? AND user_id = ?", (item_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def clear_history(user_id: int) -> None:
    async with _connect() as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        await db.commit()


async def mark_blocked(user_id: int) -> None:
    async with _connect() as db:
        await db.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_active_user_ids() -> list[int]:
    async with _connect() as db:
        async with db.execute("SELECT user_id FROM users WHERE is_blocked = 0 AND is_banned = 0") as cur:
            return [row[0] for row in await cur.fetchall()]


# --- Admin: foydalanuvchilarni boshqarish ---

USER_COLUMNS = "u.user_id, u.full_name, u.username, u.lang, u.is_blocked, u.is_banned, u.created_at, u.last_active"
SEARCH_LIMIT = 10


async def set_banned(user_id: int, banned: bool) -> bool:
    """Foydalanuvchini bloklaydi yoki blokdan chiqaradi. Bunday foydalanuvchi bo'lmasa — False."""
    async with _connect() as db:
        cur = await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (int(banned), user_id))
        await db.commit()
        return cur.rowcount > 0


async def find_users(query: str) -> list[tuple]:
    """ID, @username yoki ism bo'yicha qidiradi. Qaytaradi: USER_COLUMNS tartibidagi qatorlar."""
    query = query.strip()
    async with _connect() as db:
        if query.lstrip("-").isdigit():
            sql, params = "u.user_id = ?", (int(query),)
        elif query.startswith("@"):
            sql, params = "u.username = ? COLLATE NOCASE", (query[1:],)
        else:
            sql, params = "u.full_name LIKE ? OR u.username LIKE ?", (f"%{query}%",) * 2
        async with db.execute(
            f"SELECT {USER_COLUMNS} FROM users u WHERE {sql} ORDER BY u.last_active DESC LIMIT ?",
            (*params, SEARCH_LIMIT),
        ) as cur:
            return list(await cur.fetchall())


async def get_user_services(user_id: int) -> list[tuple[str, int, int]]:
    """Foydalanuvchi ishlatgan xizmatlar: (xizmat, jami, muvaffaqiyatsiz) — ko'pi birinchi."""
    async with _connect() as db:
        async with db.execute(
            "SELECT service, COUNT(*), SUM(success = 0) FROM stats WHERE user_id = ? GROUP BY service ORDER BY 2 DESC",
            (user_id,),
        ) as cur:
            return list(await cur.fetchall())


async def export_users() -> list[tuple]:
    """Barcha foydalanuvchilar: USER_COLUMNS + bajarilgan amallar soni."""
    async with _connect() as db:
        async with db.execute(
            f"SELECT {USER_COLUMNS}, COUNT(s.id) FROM users u LEFT JOIN stats s ON s.user_id = u.user_id "
            "GROUP BY u.user_id ORDER BY u.created_at"
        ) as cur:
            return list(await cur.fetchall())


async def get_setting(key: str) -> str | None:
    async with _connect() as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


async def set_setting(key: str, value: str) -> None:
    async with _connect() as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_stats() -> dict:
    now = datetime.now(timezone.utc)
    day = (now - timedelta(days=1)).isoformat(timespec="seconds")
    week = (now - timedelta(days=7)).isoformat(timespec="seconds")
    month = (now - timedelta(days=30)).isoformat(timespec="seconds")

    async with _connect() as db:
        async def scalar(sql: str, *params) -> int:
            async with db.execute(sql, params) as cur:
                return (await cur.fetchone())[0] or 0

        async def rows(sql: str, *params) -> list[tuple]:
            async with db.execute(sql, params) as cur:
                return list(await cur.fetchall())

        return {
            "users_total": await scalar("SELECT COUNT(*) FROM users"),
            "users_blocked": await scalar("SELECT COUNT(*) FROM users WHERE is_blocked = 1"),
            "users_banned": await scalar("SELECT COUNT(*) FROM users WHERE is_banned = 1"),
            "new_day": await scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", day),
            "new_week": await scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", week),
            "new_month": await scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", month),
            "active_day": await scalar("SELECT COUNT(*) FROM users WHERE last_active >= ?", day),
            "active_week": await scalar("SELECT COUNT(*) FROM users WHERE last_active >= ?", week),
            "langs": await rows("SELECT COALESCE(lang, '-'), COUNT(*) FROM users GROUP BY 1 ORDER BY 2 DESC"),
            "ops_total": await scalar("SELECT COUNT(*) FROM stats"),
            "ops_day": await scalar("SELECT COUNT(*) FROM stats WHERE created_at >= ?", day),
            "ops_failed": await scalar("SELECT COUNT(*) FROM stats WHERE success = 0"),
            "services": await rows(
                "SELECT service, COUNT(*), SUM(created_at >= ?) FROM stats GROUP BY service ORDER BY 2 DESC", day
            ),
        }
