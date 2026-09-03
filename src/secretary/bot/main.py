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
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import LabeledPrice

from secretary.config import Settings, get_settings
from secretary.payments.gateway import Package, get_gateway
from secretary.storage import Storage
from secretary.team import render_digest, resolve_owner
from secretary.worker.pipeline import Pipeline

log = logging.getLogger("secretary.bot")

HELP_TEXT = (
    "🎙 <b>ИИ-секретарь созвонов</b>\n\n"
    "Пришли аудио/видео созвона — получу стенограмму с репликами спикеров, "
    "саммари, решения и задачи.\n\n"
    "Поддерживается: voice, аудио, видео, документ (до {max_mb} МБ)."
    "\n\n💰 Тарифы: /buy — пакеты звонков (Telegram Stars)."
    "\n<i>Расшифровка предоставленного файла · согласие на запись — ответственность клиента.</i>"
)

BUY_TEXT = (
    "💰 <b>Пакеты звонков</b>\n\n"
    "• Старт — 3 звонка/мес (бесплатно)\n"
    "• 10 звонков/мес — 150 ⭐\n"
    "• 30 звонков/мес — 350 ⭐\n\n"
    "Нажми на пакет — оплата в Telegram Stars."
)


def _telegram_session(proxy: str | None) -> AiohttpSession:
    """AIOTG-сессия; proxy — SOCKS5-туннель к api.telegram.org (обязательно из РФ)."""
    return AiohttpSession(proxy=proxy)


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
    await storage.seed_packages()

    queue: asyncio.Queue[int] = asyncio.Queue()
    pipeline = Pipeline(settings, storage, bot, queue)
    worker = asyncio.create_task(pipeline.run_forever())
    gateway = get_gateway(settings.payment_provider)

    @dp.message(F.text == "/start")
    async def on_start(message: types.Message) -> None:
        await message.answer(HELP_TEXT.format(max_mb=settings.max_file_mb))

    @dp.message(F.text == "/help")
    async def on_help(message: types.Message) -> None:
        await message.answer(HELP_TEXT.format(max_mb=settings.max_file_mb))

    @dp.message(F.text == "/digest")
    async def on_digest(message: types.Message) -> None:
        if message.chat.type in ("group", "supergroup", "channel"):
            rows = await storage.list_orders(message.chat.id, limit=100)
        else:
            rows = await storage.list_orders(message.from_user.id, limit=100)
        enriched = [Storage.row_to_order(r) for r in rows]
        await message.answer(render_digest(enriched))

    @dp.message(F.voice | F.audio | F.video | F.document)
    async def on_media(message: types.Message) -> None:
        # v1.2.0: в группе/канале клиента заказ принадлежит чату (пакет и лимит — на чат)
        owner_id = resolve_owner(message.chat.type, message.from_user.id, message.chat.id)
        ok, limit_msg = await _check_limit(owner_id)
        if not ok:
            await message.answer(limit_msg)
            return
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
            tg_user_id=owner_id, file_name=file_id, mime=mime, size_bytes=size
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

    # --- v1.1.0: пакеты и оплата (Telegram Stars) ---

    @dp.message(F.text == "/buy")
    async def on_buy(message: types.Message) -> None:
        client = await storage.get_client(message.from_user.id)
        pkg = await storage.get_package(client["package_id"]) if client else None
        header = f"Твой пакет: <b>{pkg['name']}</b> ({pkg['calls_per_month']} зв/мес)\n\n" if pkg else ""
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text=f"10 звонков — 150 ⭐", callback_data="buy:mini"),
                    types.InlineKeyboardButton(text=f"30 звонков — 350 ⭐", callback_data="buy:pro"),
                ]
            ]
        )
        await message.answer(header + BUY_TEXT, reply_markup=kb)

    @dp.callback_query(F.data.startswith("buy:"))
    async def on_buy_callback(callback: types.CallbackQuery) -> None:
        package = Package(callback.data.split(":", 1)[1])
        result = await gateway.issue_invoice(bot, callback.message.chat.id, package)
        await callback.answer()
        if not result.ok:
            await callback.message.answer(f"❌ Не удалось выставить счёт: {result.reason}")

    @dp.pre_checkout_query()
    async def on_pre_checkout(query: types.PreCheckoutQuery) -> None:
        await bot.answer_pre_checkout_query(query.id, ok=True)

    @dp.message(F.successful_payment)
    async def on_paid(message: types.Message) -> None:
        payload = message.successful_payment.invoice_payload or ""
        if payload.startswith("package:"):
            package = Package(payload.split(":", 1)[1])
            await storage.set_client_package(message.from_user.id, package_id={Package.MINI: 2, Package.PRO: 3}[package])
            await message.answer(f"✅ Пакет «{package.title}» активирован! Присылай созвоны.")
        else:
            await message.answer("Оплата получена, но тип не распознан — напиши поддержке.")

    async def _check_limit(user_id: int) -> tuple[bool, str | None]:
        client = await storage.get_client(user_id)
        pkg = await storage.get_package(client["package_id"])
        used = await storage.count_done_calls(user_id)
        if used >= pkg["calls_per_month"]:
            return False, (
                f"Лимит пакета «{pkg['name']}» исчерпан ({used}/{pkg['calls_per_month']} звонков).\n"
                f"Расширь лимит: /buy"
            )
        return True, None

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