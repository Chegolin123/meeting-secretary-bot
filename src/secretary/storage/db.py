"""Хранилище: SQLite (v1.0.0) → PostgreSQL-совместимая схема (v1.1.0).

v1.0: заказы (orders). v1.1: клиенты (clients) и пакеты (packages) — таблицы создаются сразу,
чтобы миграция не трогала схему.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone


class Storage:
    def __init__(self, db_path: str):
        self._path = db_path

    async def init(self) -> None:
        import aiosqlite  # noqa: PLC0415

        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_user_id INTEGER NOT NULL,
                    file_name TEXT,
                    mime TEXT,
                    size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'received',
                    provider TEXT,
                    audio_duration_sec REAL,
                    summary_json TEXT,
                    transcript TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    tg_user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    package_id INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price_stars INTEGER DEFAULT 0,
                    calls_per_month INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def create_order(
        self, tg_user_id: int, file_name: str | None, mime: str | None, size_bytes: int
    ) -> int:
        import aiosqlite  # noqa: PLC0415

        now = self._now()
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO orders (tg_user_id, file_name, mime, size_bytes, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'received', ?, ?)",
                (tg_user_id, file_name, mime, size_bytes, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def set_status(self, order_id: int, status: str, error: str | None = None) -> None:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            if error is None:
                await db.execute(
                    "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (status, self._now(), order_id)
                )
            else:
                await db.execute(
                    "UPDATE orders SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                    (status, error, self._now(), order_id),
                )
            await db.commit()

    async def save_result(
        self,
        order_id: int,
        provider: str,
        audio_duration_sec: float,
        summary_json: str,
        transcript: str,
    ) -> None:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE orders SET status = 'done', provider = ?, audio_duration_sec = ?, "
                "summary_json = ?, transcript = ?, updated_at = ? WHERE id = ?",
                (provider, audio_duration_sec, summary_json, transcript, self._now(), order_id),
            )
            await db.commit()

    async def get_order(self, order_id: int) -> dict | None:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_orders(self, tg_user_id: int | None = None, limit: int = 50) -> list[dict]:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            if tg_user_id is None:
                cur = await db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
            else:
                cur = await db.execute(
                    "SELECT * FROM orders WHERE tg_user_id = ? ORDER BY id DESC LIMIT ?", (tg_user_id, limit)
                )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def cleanup_expired(self, retention_days: int) -> int:
        """v1.0: удаляем транскрипты/саммари старше RETENTION_DAYS (файлы чистит pipeline)."""
        import aiosqlite  # noqa: PLC0415

        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("DELETE FROM orders WHERE created_at < ?", (cutoff,))
            await db.commit()
            return cur.rowcount

    # --- v1.1.0: клиенты и пакеты ---

    async def seed_packages(self) -> None:
        import aiosqlite  # noqa: PLC0415

        now = self._now()
        async with aiosqlite.connect(self._path) as db:
            for pid, name, stars, calls in (
                (1, "starter", 0, 3),
                (2, "mini", 150, 10),
                (3, "pro", 350, 30),
            ):
                await db.execute(
                    "INSERT OR IGNORE INTO packages (id, name, price_stars, calls_per_month, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, name, stars, calls, now),
                )
            await db.commit()

    async def ensure_client(self, tg_user_id: int, package_id: int = 1) -> None:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO clients (tg_user_id, package_id, created_at) VALUES (?, ?, ?)",
                (tg_user_id, package_id, self._now()),
            )
            await db.commit()

    async def set_client_package(self, tg_user_id: int, package_id: int) -> None:
        import aiosqlite  # noqa: PLC0415

        await self.ensure_client(tg_user_id, package_id)
        async with aiosqlite.connect(self._path) as db:
            await db.execute("UPDATE clients SET package_id = ? WHERE tg_user_id = ?", (package_id, tg_user_id))
            await db.commit()

    async def get_client(self, tg_user_id: int) -> dict | None:
        import aiosqlite  # noqa: PLC0415

        await self.ensure_client(tg_user_id)
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM clients WHERE tg_user_id = ?", (tg_user_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_package(self, package_id: int) -> dict | None:
        import aiosqlite  # noqa: PLC0415

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM packages WHERE id = ?", (package_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def count_done_calls(self, tg_user_id: int, days: int = 30) -> int:
        """Сколько заказов клиент сделал за последние N дней (лимит пакета)."""
        import aiosqlite  # noqa: PLC0415

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE tg_user_id = ? AND status = 'done' AND created_at >= ?",
                (tg_user_id, cutoff),
            )
            row = await cur.fetchone()
            return int(row[0] or 0)

    @staticmethod
    def row_to_order(row: dict) -> dict:
        row = dict(row)
        if row.get("summary_json"):
            try:
                row["summary"] = json.loads(row["summary_json"])
            except json.JSONDecodeError:
                row["summary"] = None
        return row