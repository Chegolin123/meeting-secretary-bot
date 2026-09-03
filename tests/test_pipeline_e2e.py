"""E2E-тест ядра ЛОКАЛЬНО (без внешних ключей): полный цикл заказа.

Заказ → скачивание файла → STT (фейк с диаризацией) → DeepSeek (фейк) →
отчёт (TG HTML) → .docx → статус done в БД.
"""

import asyncio
from pathlib import Path

import pytest

from secretary.config import Settings
from secretary.llm.deepseek import MeetingSummary
from secretary.storage import Storage
from secretary.stt.base import TranscriptResult, Utterance
from secretary.worker.pipeline import Pipeline


class FakeStt:
    provider_name = "fake"

    async def transcribe_file(self, audio_bytes: bytes, language: str) -> TranscriptResult:
        assert audio_bytes == b"fake-audio-bytes"
        return TranscriptResult(
            text="Тест один. Тест два.",
            utterances=[Utterance("1", "Тест один."), Utterance("2", "Тест два.")],
            audio_duration_sec=60.5,
            provider="fake",
        )


class FakeLlm:
    async def summarize(self, dialogue: str) -> MeetingSummary:
        assert "[Спикер 1]" in dialogue
        return MeetingSummary(
            summary="Обсудили тест.",
            decisions=["Ничего не решено"],
            tasks=[{"task": "Проверить e2e", "owner": "Мя", "priority": "high"}],
            key_topics=["тест"],
        )


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.docs: list[tuple[str, bytes]] = []

    async def download(self, file_id: str, destination) -> None:
        destination.write_bytes(b"fake-audio-bytes")

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append(text)

    async def send_document(self, chat_id: int, document, caption: str = "") -> None:
        self.docs.append((document.filename, document.data))


async def test_pipeline_full_order(tmp_path):
    data_dir = Path(tmp_path) / "data"
    settings = Settings(db_path=str(tmp_path / "s.db"), data_dir=str(data_dir))
    storage = Storage(settings.db_path)
    await storage.init()
    bot = FakeBot()
    queue: asyncio.Queue[int] = asyncio.Queue()
    pipeline = Pipeline(settings, storage, bot, queue, stt=FakeStt(), llm=FakeLlm())

    order_id = await storage.create_order(tg_user_id=42, file_name="file_id_1", mime="audio/ogg", size_bytes=123)
    await queue.put(order_id)
    await pipeline.process(order_id)

    order = await storage.get_order(order_id)
    assert order["status"] == "done"
    assert order["provider"] == "fake"
    assert order["audio_duration_sec"] == 60.5
    assert "Обсудили тест." in order["summary_json"]
    assert "[Спикер 1] Тест один." in order["transcript"]

    # бот получил отчёт в HTML и .docx
    html = "".join(bot.sent)
    assert "Итоги созвона #" in html
    assert "Обсудили тест." in html
    assert "Проверить e2e" in html
    assert any(name.endswith(".docx") for name, _ in bot.docs)
    assert any(b"PK" == doc_bytes[:2] for _, doc_bytes in bot.docs)

    # локальная копия файла удалена после обработки
    assert not list((data_dir / "media").glob("*.ogg"))


async def test_pipeline_error_marks_order(tmp_path):
    class BrokenStt:
        provider_name = "broken"

        async def transcribe_file(self, audio_bytes, language):
            raise RuntimeError("boom")

    settings = Settings(db_path=str(tmp_path / "s.db"), data_dir=str(tmp_path / "data"))
    storage = Storage(settings.db_path)
    await storage.init()
    bot = FakeBot()
    pipeline = Pipeline(settings, storage, bot, asyncio.Queue(), stt=BrokenStt(), llm=FakeLlm())

    order_id = await storage.create_order(tg_user_id=7, file_name="f1", mime="audio/ogg", size_bytes=1)
    await pipeline.process(order_id)

    order = await storage.get_order(order_id)
    assert order["status"] == "error"
    assert "boom" in order["error"]
    assert any("не удался" in m for m in bot.sent)