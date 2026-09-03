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


class _FakeResp:
    status_code = 500
    text = "boom"

    def json(self):
        raise AssertionError("не должен вызываться")


class _FakeClient:
    def __init__(self):
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        return _FakeResp()


async def test_upload_retries_three_times():
    from secretary.stt.assembly import UPLOAD_RETRIES, AssemblyAIProvider
    from secretary.stt.base import STTError

    fake = _FakeClient()
    provider = AssemblyAIProvider(api_key="k", client=fake)
    try:
        await provider._upload(b"audio")
        assert False, "должна быть ошибка после ретраев"
    except STTError as e:
        assert "3 попытки" in str(e)
    assert fake.calls == UPLOAD_RETRIES


async def test_provider_accepts_proxy_arg():
    from secretary.stt.assembly import AssemblyAIProvider

    p = AssemblyAIProvider(api_key="k", proxy="socks5://127.0.0.1:1082")
    assert p._proxy == "socks5://127.0.0.1:1082"