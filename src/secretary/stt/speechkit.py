"""Резервный STT-провайдер (v1.3.0): Yandex SpeechKit, асинхронное распознавание.

Включается: STT_PROVIDER=speechkit + SPEECHKIT_FOLDER_ID + SPEECHKIT_API_KEY.
⚠️ Сверить параметры запроса и формат chunks с актуальной документацией при первом
прогоне с ключом (Д2): API Яндекса меняется; диаризация в асинхронном распознавании
зависит от модели (baseline/general + diarization) и помечена как «проверить».
"""

from __future__ import annotations

import asyncio

import httpx
from secretary.stt.base import STTError, TranscriptResult, Utterance

POLL_INTERVAL_SEC = 5.0
POLL_TIMEOUT_SEC = 60 * 30

#: домены Yandex Cloud API
STT_HOST = "https://stt.api.cloud.yandex.net"
OPERATION_HOST = "https://operation.api.cloud.yandex.net"


class SpeechKitProvider:
    provider_name = "speechkit"

    def __init__(
        self,
        api_key: str = "",
        folder_id: str = "",
        iam_token: str = "",
        client: httpx.AsyncClient | None = None,
    ):
        if not api_key and not iam_token:
            raise STTError("SPEECHKIT_API_KEY (или SPEECHKIT_IAM_TOKEN) не задан")
        if not folder_id:
            raise STTError("SPEECHKIT_FOLDER_ID не задан")
        self._api_key = api_key
        self._iam_token = iam_token
        self._folder_id = folder_id
        self._client = client

    async def _session(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _auth(self) -> dict[str, str]:
        if self._iam_token:
            return {"authorization": f"Bearer {self._iam_token}"}
        return {"authorization": f"Api-Key {self._api_key}"}

    async def _start(self, audio_bytes: bytes, language: str, diarization: bool) -> str:
        """POST асинхронного распознавания → id операции."""
        s = await self._session()
        params = {
            "lang": language,
            "folderId": self._folder_id,
            "recognizer": "general",
            # диаризация: параметр из документации SpeechKit (проверить при Д2-прогоне)
            **({"diarization": "true"} if diarization else {}),
        }
        r = await s.post(
            f"{STT_HOST}/speech/v1/stt:async:recognize",
            params=params,
            headers=self._auth(),
            content=audio_bytes,
        )
        if r.status_code != 200:
            raise STTError(f"SpeechKit start failed: {r.status_code} {r.text[:200]}")
        operation_id = r.json().get("id")
        if not operation_id:
            raise STTError(f"SpeechKit: нет id операции: {r.text[:200]}")
        return operation_id

    async def _wait(self, operation_id: str) -> dict:
        s = await self._session()
        deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SEC
        while True:
            r = await s.get(f"{OPERATION_HOST}/operations/{operation_id}")
            if r.status_code != 200:
                raise STTError(f"SpeechKit poll failed: {r.status_code} {r.text[:200]}")
            data = r.json()
            if data.get("done"):
                if "error" in data:
                    raise STTError(f"SpeechKit operation error: {data['error']}")
                return data.get("response", {})
            if asyncio.get_event_loop().time() > deadline:
                raise STTError("SpeechKit: таймаут ожидания операции")
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def transcribe_file(self, audio_bytes: bytes, language: str) -> TranscriptResult:
        operation_id = await self._start(audio_bytes, language, diarization=True)
        response = await self._wait(operation_id)
        return parse_response(response, provider=self.provider_name)


def parse_response(response: dict, provider: str = "speechkit") -> TranscriptResult:
    """Чистая функция: ответ операции SpeechKit → TranscriptResult (тестируется без сети).

    Формат: response.chunks[] = {"alternatives": [{"text": ...}], "channelTag": "1"}
    При диаризации список спикеров может приходить отдельным полем (сверить в Д2).
    """
    chunks = response.get("chunks", []) or []
    utterances: list[Utterance] = []
    full_texts: list[str] = []
    for chunk in chunks:
        alt = (chunk.get("alternatives") or [{}])[0]
        text = (alt.get("text") or "").strip()
        if not text:
            continue
        channel = str(chunk.get("channelTag", "1") or "1")
        if len(chunks) > 1:
            utterances.append(Utterance(speaker=channel, text=text))  # каналы ≈ спикеры (грубо)
        full_texts.append(text)
    return TranscriptResult(
        text=" ".join(full_texts),
        utterances=utterances,
        audio_duration_sec=0.0,  # SpeechKit не возвращает длительность в ответе операции
        provider=provider,
        raw=response,
    )