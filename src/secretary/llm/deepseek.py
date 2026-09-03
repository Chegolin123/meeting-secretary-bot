"""LLM: DeepSeek (OpenAI-совместимый API) — постобработка транскрипта."""

from __future__ import annotations

import dataclasses
import json
import re

import httpx

SYSTEM_PROMPT = (
    "Ты — ИИ-секретарь созвонов. По транскрипту разговора составь структурированный отчёт. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-разметки, по схеме:\n"
    '{"summary": "краткое саммари разговора 3-5 предложений", '
    '"decisions": ["принятые решения"], '
    '"tasks": [{"task": "задача", "owner": "ответственный", "priority": "high|medium|low"}], '
    '"key_topics": ["ключевые темы"]}\n'
    "Спикеры отличай по меткам [Спикер N]. Не выдумывай факты, которых нет в транскрипте."
)


class DeepSeekError(RuntimeError):
    pass


@dataclasses.dataclass
class MeetingSummary:
    summary: str
    decisions: list[str]
    tasks: list[dict]
    key_topics: list[str]


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        client: httpx.AsyncClient | None = None,
    ):
        if not api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY не задан")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client

    async def _session(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def summarize(self, dialogue: str, system_prompt: str | None = None) -> MeetingSummary:
        s = await self._session()
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt or build_system_prompt()},
                {"role": "user", "content": dialogue[: 120_000]},  # предохранитель от гигантских входов
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        r = await s.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers={"authorization": f"Bearer {self._api_key}"},
        )
        if r.status_code != 200:
            raise DeepSeekError(f"DeepSeek failed: {r.status_code} {r.text[:200]}")
        content = r.json()["choices"][0]["message"]["content"]
        return parse_summary(content)


def parse_summary(content: str) -> MeetingSummary:
    """Разбор ответа LLM: вырезает markdown-обёртки, если модель их всё-таки прислала."""
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise DeepSeekError(f"LLM вернул не-JSON: {content[:200]}")
        data = json.loads(text[start : end + 1])
    return MeetingSummary(
        summary=str(data.get("summary", "")),
        decisions=[str(x) for x in data.get("decisions", [])],
        tasks=[dict(t) for t in data.get("tasks", [])],
        key_topics=[str(x) for x in data.get("key_topics", [])],
    )