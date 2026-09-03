"""STT-абстракция (v1.3.0: провайдеры переключаются одной настройкой)."""

from dataclasses import dataclass, field
from typing import Protocol

# from __future__ import annotations — не нужно: 3.11


@dataclass
class Utterance:
    speaker: str  # "1", "2", ... или "" если диаризация выключена
    text: str


@dataclass
class TranscriptResult:
    text: str
    utterances: list[Utterance] = field(default_factory=list)
    audio_duration_sec: float = 0.0
    provider: str = ""
    raw: dict | None = None

    @property
    def with_speakers(self) -> bool:
        return bool(self.utterances)

    def to_dialogue(self) -> str:
        """Текст для LLM: строки вида «Спикер N: ...» или просто текст."""
        if self.utterances:
            return "\n".join(f"[Спикер {u.speaker}] {u.text}" for u in self.utterances)
        return self.text


class STTError(RuntimeError):
    pass


class STTProvider(Protocol):
    provider_name: str

    async def transcribe_file(self, audio_bytes: bytes, language: str) -> TranscriptResult:
        """Транскрибация аудио с диаризацией спикеров (если провайдер умеет)."""
        ...


def get_provider(settings) -> STTProvider:
    from secretary.stt.assembly import AssemblyAIProvider

    if settings.stt_provider == "assemblyai":
        return AssemblyAIProvider(
            api_key=settings.assemblyai_api_key,
            base_url=settings.assemblyai_base_url,
        )
    # v1.3.0: speechkit — заглушка с понятной ошибкой до сверки тарифов
    if settings.stt_provider == "speechkit":
        raise NotImplementedError(
            "SpeechKit подключён после сверки тарифов (см. Дорожную карту v1.3.0). "
            "Пока используйте STT_PROVIDER=assemblyai."
        )
    raise STTError(f"Неизвестный STT_PROVIDER={settings.stt_provider!r}")