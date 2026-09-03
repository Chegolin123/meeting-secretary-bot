"""STT: внешние провайдеры."""

from secretary.stt.base import STTError, STTProvider, TranscriptResult, Utterance, get_provider

__all__ = ["STTError", "STTProvider", "TranscriptResult", "Utterance", "get_provider"]