"""Telegram-бот (aiogram 3): приём аудио → очередь → отчёты.

Туннель: если задан TELEGRAM_PROXY (SOCKS5 через NL VPS), весь трафик к
api.telegram.org идёт через него — обязательно при деплое в РФ (см. docs/DEPLOY.md).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F, types

from secretary.config import Settings, get_settings
from secretary.storage import Storage
from secretary.worker.pipeline import Pipeline

log = logging.getLogger("secretary.bot")

HELP_TEXT = (
    "🎙 <b>ИИ-секретарь созвонов</b>\n\n"
    "Пришли аудио/видео созвона — получу стенограмму с репликами спикеров, "
    "саммари, решения и задачи.\n\n"
    "Поддерживается: voice, аудио, видео, документ (до {max_mb} МБ)."
    "\n\n<i>Расшифровка предоставленного файла · согласие на запись — ответственность клиента.</i>"
)


def _telegram_session(proxy: str | None) -> aiohttp.ClientSession:
    if proxy:
        from aiohttp_socks import ProxyConnector  # noqa: PLC0415

        connector = ProxyConnector.from_url(proxy)
        return aiohttp.ClientSession(connector=connector)
    return aiohttp.ClientSession()


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)

    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN не задан — смотри .env.example")
        sys.exit(1)

    session = _telegram_session(settings.telegram_proxy)
    bot = Bot(token=settings.telegram_bot_token, session=session)
    dp = Dispatcher()

    storage = Storage(settings.db_path)
    await storage.init()

    queue: asyncio.Queue[int] = asyncio.Queue()
    pipeline = Pipeline(settings, storage, bot, queue)
    worker = asyncio.create_task(pipeline.run_forever())

    @dp.message(F.text == "/start")
    async def on_start(message: types.Message) -> None:
        await message.answer(HELP_TEXT.format(max_mb=settings.max_file_mb))

    @dp.message(F.text == "/help")
    async def on_help(message: types.Message) -> None:
        await message.answer(HELP_TEXT.format(max_mb=settings.max_file_mb))

    @dp.message(F.voice | F.audio | F.video | F.document)
    async def on_media(message: types.Message) -> None:
        file_id, mime, name = _pick_file(message)
        size = getattr(getattr(message, _kind_of(message), None), "file_size", 0) or 0
        if size > settings.max_file_bytes:
            await message.answer(
                f"❌ Файл больше {settings.max_file_mb} МБ (лимит Bot API). "
                f"Пришли фрагментами или ссылку на файл."
            )
            return
        if not file_id:
            await message.answer("⚠️ Не удалось прочитать файл — попробуй другой формат (mp3/ogg/mp4).")
            return
        order_id = await storage.create_order(
            tg_user_id=message.from_user.id, file_name=file_id, mime=mime, size_bytes=size
        )
        await message.answer(f"📥 Заказ #{order_id} принят. Обработаю и пришлю отчёт.")
        await queue.put(order_id)

    @dp.message(F.text == "/orders")
    async def on_orders(message: types.Message) -> None:
        rows = [r for r in await storage.list_orders(message.from_user.id, limit=10) if r["status"] != "error"]
        if not rows:
            await message.answer("Заказов пока нет.")
            return
        lines = [f"#{r['id']} · {r['status']} · {r['created_at'][:16].replace('T', ' ')}" for r in rows]
        await message.answer("📋 Последние заказы:\n" + "\n".join(lines))

    @dp.startup()
    async def on_startup() -> None:
        log.info("Бот запущен (proxy=%s)", settings.telegram_proxy or "нет")

    @dp.shutdown()
    async def on_shutdown() -> None:
        worker.cancel()
        await session.close()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        await session.close()


def _kind_of(message: types.Message) -> str:
    for kind in ("voice", "audio", "video", "document"):
        if getattr(message, kind):
            return kind
    return ""


def _pick_file(message: types.Message) -> tuple[str | None, str | None, str | None]:
    kind = _kind_of(message)
    obj = getattr(message, kind)
    if obj is None:
        return None, None, None
    mime = getattr(obj, "mime_type", None)
    name = getattr(obj, "file_name", None)
    return obj.file_id, mime, name


if __name__ == "__main__":
    asyncio.run(main())