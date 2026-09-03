"""AssemblyAI-клиент (v1.0.0). Платно: $0.21/час + $0.02/час диаризация (Universal-3.5 Pro)."""

from __future__ import annotations

import asyncio

import httpx
from secretary.stt.base import STTError, TranscriptResult, Utterance

POLL_INTERVAL_SEC = 5.0
POLL_TIMEOUT_SEC = 60 * 30  # 30 минут максимум на час аудио


class AssemblyAIProvider:
    provider_name = "assemblyai"

    def __init__(self, api_key: str, base_url: str = "https://api.assemblyai.com", client: httpx.AsyncClient | None = None):
        if not api_key:
            raise STTError("ASSEMBLYAI_API_KEY не задан")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        # client передаётся извне для тестов; production создаёт свой
        self._client = client

    async def _session(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"authorization": self._api_key},
                timeout=httpx.Timeout(120.0, connect=30.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _upload(self, audio_bytes: bytes) -> str:
        s = await self._session()
        r = await s.post("/v2/upload", content=audio_bytes, headers={"content-type": "application/octet-stream"})
        if r.status_code != 200:
            raise STTError(f"AssemblyAI upload failed: {r.status_code} {r.text[:200]}")
        return r.json()["upload_url"]

    async def _create_transcript(self, audio_url: str, language: str) -> str:
        s = await self._session()
        payload = {
            "audio_url": audio_url,
            "language_code": language,
            "speaker_labels": True,  # диаризация — в Н1 (решение 03.09.2026)
            "speakers_expected": 2,
        }
        r = await s.post("/v2/transcript", json=payload)
        if r.status_code != 200:
            raise STTError(f"AssemblyAI transcribe failed: {r.status_code} {r.text[:200]}")
        return r.json()["id"]

    async def _wait(self, transcript_id: str) -> dict:
        s = await self._session()
        deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SEC
        while True:
            r = await s.get(f"/v2/transcript/{transcript_id}")
            if r.status_code != 200:
                raise STTError(f"AssemblyAI poll failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status == "error":
                raise STTError(f"AssemblyAI error: {data.get('error', 'unknown')}")
            if asyncio.get_event_loop().time() > deadline:
                raise STTError("AssemblyAI: таймаут ожидания транскрипта")
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def transcribe_file(self, audio_bytes: bytes, language: str) -> TranscriptResult:
        audio_url = await self._upload(audio_bytes)
        transcript_id = await self._create_transcript(audio_url, language)
        data = await self._wait(transcript_id)
        return parse_transcript(data, provider=self.provider_name)


def parse_transcript(data: dict, provider: str = "assemblyai") -> TranscriptResult:
    """Чистая функция: JSON AssemblyAI -> TranscriptResult (тестируется без сети)."""
    utterances = [
        Utterance(speaker=str(u.get("speaker", "")), text=u.get("text", ""))
        for u in data.get("utterances", [])
        if u.get("text") and u["text"].strip()
    ]
    return TranscriptResult(
        text=data.get("text", ""),
        utterances=utterances,
        audio_duration_sec=float(data.get("audio_duration", 0.0) or 0.0),
        provider=provider,
        raw=data,
    )