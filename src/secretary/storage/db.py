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

    @staticmethod
    def row_to_order(row: dict) -> dict:
        row = dict(row)
        if row.get("summary_json"):
            try:
                row["summary"] = json.loads(row["summary_json"])
            except json.JSONDecodeError:
                row["summary"] = None
        return row