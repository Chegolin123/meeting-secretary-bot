"""Пайплайн обработки заказа: скачать файл → STT → DeepSeek → отчёт.

v1.0: asyncio-очередь + один воркер (без Celery/PostgreSQL — решение Н1).
v1.1: вынос в Celery, когда появится параллельная нагрузка (Н3 дорожной карты).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from secretary.config import Settings
from secretary.llm.deepseek import DeepSeekClient, MeetingSummary
from secretary.report.formats import render_docx, render_tg_html, render_txt
from secretary.storage import Storage
from secretary.stt.base import STTError, TranscriptResult, get_provider

log = logging.getLogger("secretary.pipeline")

TEMP_SUFFIXES = ".ogg .m4a .mp3 .wav .mp4 .mov .webm .opus .oga .aac .flac"


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        bot,
        queue: asyncio.Queue[int],
        stt=None,
        llm: DeepSeekClient | None = None,
    ):
        """stt/llm — опциональные подмены (тесты, будущие провайдеры); по умолчанию из конфига."""
        self.settings = settings
        self.storage = storage
        self.bot = bot
        self.queue = queue
        self._stt = stt if stt is not None else get_provider(settings)
        self._llm = llm if llm is not None else DeepSeekClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        self._tmp_root = Path(settings.data_dir) / "media"
        self._tmp_root.mkdir(parents=True, exist_ok=True)

    async def run_forever(self) -> None:
        while True:
            order_id = await self.queue.get()
            try:
                await self.process(order_id)
            except Exception as e:  # noqa: BLE001 — воркер живёт при любой ошибке
                await self._fail(order_id, f"Внутренняя ошибка: {e}")
            finally:
                self.queue.task_done()

    async def process(self, order_id: int) -> None:
        """Полный цикл заказа. Гарантирует статус error в БД при любой ошибке."""
        try:
            await self._process(order_id)
        except Exception as e:  # noqa: BLE001
            log.exception("Заказ %s упал: %s", order_id, e)
            await self._fail(order_id, f"{type(e).__name__}: {e}")

    async def _process(self, order_id: int) -> None:
        order = await self.storage.get_order(order_id)
        if order is None:
            return
        chat_id = order["tg_user_id"]
        await self._status(chat_id, f"⏳ Заказ #{order_id}: скачиваю файл…")

        # 1. Скачивание файла
        await self.storage.set_status(order_id, "downloading")
        file_id = order["file_name"]  # храним file_id в file_name (см. bot создание заказа)
        ext = (order["mime"] or "").split("/")[-1] or "bin"
        tmp_path = self._tmp_root / f"{order_id}.{ext}"
        await self.bot.download(file_id, destination=tmp_path)
        audio_bytes = tmp_path.read_bytes()
        try:
            # 2. STT (онлайн, диаризация)
            await self.storage.set_status(order_id, "stt")
            await self._status(chat_id, f"⏳ Заказ #{order_id}: распознаю речь (около 1 мин на 10 мин аудио)…")
            result: TranscriptResult = await self._stt.transcribe_file(
                audio_bytes, language=self.settings.language_code
            )

            # 3. LLM-постобработка
            await self.storage.set_status(order_id, "llm")
            await self._status(chat_id, f"⏳ Заказ #{order_id}: составляю саммари и задачи…")
            summary: MeetingSummary = await self._llm.summarize(result.to_dialogue())

            # 4. Отчёты
            await self.storage.save_result(
                order_id,
                provider=result.provider,
                audio_duration_sec=result.audio_duration_sec,
                summary_json=_summary_to_json(summary),
                transcript=render_txt(result),
            )
            tg_html = render_tg_html(result, summary, order_id)
            await self.bot.send_message(chat_id, tg_html)
            try:
                docx_bytes = render_docx(result, summary, order_id)
                await self.bot.send_document(
                    chat_id,
                    docx_bytes,
                    filename=f"созвон-{order_id}.docx",
                    caption=f"📄 Отчёт #{order_id} (.docx)",
                )
            except RuntimeError:
                # python-docx недоступен — TG-отчёт уже отправлен, это не критично
                pass
            await self._status(chat_id, f"✅ Заказ #{order_id} готов!")
        finally:
            # 5. Хранение 7 дней: локальные копии удаляем сразу, БД чистит cleanup
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    async def _status(self, chat_id: int, text: str) -> None:
        try:
            await self.bot.send_message(chat_id, text)
        except Exception:  # noqa: BLE001 — статусы не критичны
            pass

    async def _fail(self, order_id: int, message: str) -> None:
        await self.storage.set_status(order_id, "error", error=message[:1000])
        order = await self.storage.get_order(order_id)
        if order:
            try:
                await self.bot.send_message(
                    order["tg_user_id"],
                    f"❌ Заказ #{order_id} не удался: {message}",
                )
            except Exception:  # noqa: BLE001
                pass


def _summary_to_json(summary: MeetingSummary) -> str:
    import json  # noqa: PLC0415

    return json.dumps(
        {
            "summary": summary.summary,
            "decisions": summary.decisions,
            "tasks": summary.tasks,
            "key_topics": summary.key_topics,
        },
        ensure_ascii=False,
    )