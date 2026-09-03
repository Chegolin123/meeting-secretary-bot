"""Тесты: парсинг JSON-ответа DeepSeek (без сети)."""

import pytest

from secretary.llm.deepseek import DeepSeekError, MeetingSummary, parse_summary

GOOD_JSON = (
    '{"summary": "Обсудили сроки", "decisions": ["Берём 2 недели"], '
    '"tasks": [{"task": "Подготовить макет", "owner": "Аня", "priority": "high"}], '
    '"key_topics": ["сроки", "макет"]}'
)


def test_parse_plain_json():
    s = parse_summary(GOOD_JSON)
    assert isinstance(s, MeetingSummary)
    assert s.summary == "Обсудили сроки"
    assert s.decisions == ["Берём 2 недели"]
    assert s.tasks[0]["owner"] == "Аня"


def test_parse_with_markdown_fence():
    s = parse_summary(f"```json\n{GOOD_JSON}\n```")
    assert s.tasks[0]["priority"] == "high"


def test_parse_with_surrounding_text():
    s = parse_summary(f"Вот отчёт:\n{GOOD_JSON}")
    assert "сроки" in s.key_topics


def test_parse_broken_json_raises():
    with pytest.raises(DeepSeekError):
        parse_summary("совсем не json")