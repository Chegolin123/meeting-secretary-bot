"""Тесты: парсинг ответа AssemblyAI (без сети)."""

from secretary.stt.assembly import parse_transcript
from secretary.stt.base import TranscriptResult

COMPLETED = {
    "id": "t1",
    "status": "completed",
    "text": "Привет. Привет, давай обсудим сроки.",
    "audio_duration": 62.4,
    "utterances": [
        {"speaker": "A", "text": "Привет."},
        {"speaker": "B", "text": "Привет, давай обсудим сроки."},
    ],
}


def test_parse_transcript_extracts_utterances():
    result = parse_transcript(COMPLETED)
    assert isinstance(result, TranscriptResult)
    assert result.with_speakers is True
    assert len(result.utterances) == 2
    assert result.utterances[0].speaker == "A"
    assert result.audio_duration_sec == 62.4
    assert result.provider == "assemblyai"


def test_parse_transcript_without_speakers():
    data = {"status": "completed", "text": "Просто текст", "audio_duration": 10}
    result = parse_transcript(data)
    assert result.with_speakers is False
    assert result.to_dialogue() == "Просто текст"


def test_to_dialogue_formats_speakers():
    result = parse_transcript(COMPLETED)
    dialogue = result.to_dialogue()
    assert "[Спикер A]" in dialogue
    assert "[Спикер B]" in dialogue


def test_empty_utterances_skipped():
    data = {"status": "completed", "text": "x", "utterances": [{"speaker": "A", "text": "  "}]}
    result = parse_transcript(data)
    assert result.utterances == []