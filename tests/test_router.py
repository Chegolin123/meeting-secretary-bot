"""Тесты роутера vault: промпт, парсинг, валидация (не додумываем)."""

from secretary.router import (
    RouteDecision,
    build_route_prompt,
    parse_route_answer,
    validate_decision,
)


def test_build_prompt_contains_catalog_and_summary():
    prompt = build_route_prompt(
        {"summary": "Обсудили лендинг", "key_topics": ["лендинг"]},
        [{"path": "01 — Проекты/Leady Landing.md", "name": "Leady Landing"}],
        order_id=7,
    )
    assert "Leady Landing" in prompt
    assert "лендинг" in prompt
    assert '"mode"' in prompt  # JSON-схема ответа


def test_parse_decision_append():
    d = parse_route_answer('{"mode": "append", "target_path": "01 — Проекты/Leady Landing.md", "confidence": 0.9, "reason": "тема совпадает"}')
    assert d.mode == "append"
    assert d.target_path == "01 — Проекты/Leady Landing.md"
    assert d.confident is True


def test_parse_decision_new():
    d = parse_route_answer(
        "```json\n" + '{"mode": "new", "folder": "05 — Идеи и планы", '
        '"note_name": "Дзен-фабрика план", "confidence": 0.8}' + "\n```"
    )
    assert d.mode == "new"
    assert d.folder == "05 — Идеи и планы"
    assert d.confident


def test_parse_broken_json_becomes_ask():
    d = parse_route_answer("много текста без json")
    assert d.mode == "ask"
    assert not d.confident


def test_parse_unknown_mode_becomes_ask():
    d = parse_route_answer('{"mode": "delete_all", "confidence": 1}')
    assert d.mode == "ask"


def test_validate_append_target_must_exist():
    catalog = [{"path": "01 — Проекты/Real.md", "name": "Real"}]
    d = RouteDecision(mode="append", target_path="Нет такой.md", confidence=0.9)
    result = validate_decision(d, catalog)
    assert result.mode == "ask"  # несуществующая цель → вопрос, не угадывание


def test_validate_new_folder_must_be_in_catalog():
    catalog = [{"path": "01 — Проекты/Real.md", "name": "Real"}]
    d = RouteDecision(mode="new", folder="99 — Архив", confidence=0.9)
    result = validate_decision(d, catalog)
    assert result.mode == "ask"