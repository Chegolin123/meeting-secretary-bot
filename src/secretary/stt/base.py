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
    if settings.stt_provider == "assemblyai":
        from secretary.stt.assembly import AssemblyAIProvider

        return AssemblyAIProvider(
            api_key=settings.assemblyai_api_key,
            base_url=settings.assemblyai_base_url,
        )
    if settings.stt_provider == "speechkit":  # v1.3.0: резерв для чувствительных записей
        from secretary.stt.speechkit import SpeechKitProvider

        return SpeechKitProvider(
            api_key=getattr(settings, "speechkit_api_key", ""),
            folder_id=getattr(settings, "speechkit_folder_id", ""),
            iam_token=getattr(settings, "speechkit_iam_token", ""),
        )
    raise STTError(f"Неизвестный STT_PROVIDER={settings.stt_provider!r}")