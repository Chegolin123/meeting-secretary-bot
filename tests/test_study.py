"""Тесты режима «конспекты лекций» (study_mode)."""

from secretary.study import (
    LectureSummary,
    build_study_system_prompt,
    parse_lecture,
    render_docx_lecture,
    render_tg_lecture,
)
from secretary.stt.base import TranscriptResult, Utterance


def _lecture_json() -> str:
    return (
        '{"subject": "Матанализ", "lecture_topic": "Производная", '
        '"key_points": ["Производная — скорость изменения"], '
        '"definitions": [{"term": "Производная", "definition": "предел приращения"}], '
        '"formulas": ["f\'(x) = lim Δy/Δx"], '
        '"review_questions": ["Что такое производная?"], '
        '"unclear": ["как брать производную сложной функции"]}'
    )


def test_study_prompt_mentions_lecture():
    prompt = build_study_system_prompt()
    assert "лекц" in prompt.lower()
    assert "key_points" in prompt


def test_parse_lecture():
    l = parse_lecture(_lecture_json())
    assert l.subject == "Матанализ"
    assert l.lecture_topic == "Производная"
    assert l.key_points == ["Производная — скорость изменения"]
    assert l.definitions[0]["term"] == "Производная"
    assert l.formulas
    assert len(l.review_questions) == 1
    assert l.unclear


def test_parse_lecture_broken_returns_empty():
    l = parse_lecture("не json вообще")
    assert l.key_points == []
    assert l.unclear  # честное «не удалось разобрать», не выдумка


def test_parse_lecture_fenced():
    l = parse_lecture("```json\n" + _lecture_json() + "\n```")
    assert l.subject == "Матанализ"


def test_render_tg_lecture():
    tr = TranscriptResult(text="x", utterances=[Utterance("1", "привет")], audio_duration_sec=5400, provider="a")
    html = render_tg_lecture(tr, parse_lecture(_lecture_json()), order_id=9)
    assert "Конспект #9" in html
    assert "Матанализ" in html
    assert "Ключевые тезисы" in html
    assert "Определения" in html
    assert "Вопросы для повторения" in html
    assert "90 мин" in html  # 5400с


def test_render_docx_lecture():
    import zipfile

    tr = TranscriptResult(text="x", utterances=[], audio_duration_sec=60, provider="a")
    docx = render_docx_lecture(tr, parse_lecture(_lecture_json()), order_id=3)
    data = docx.getvalue()
    assert data.startswith(b"PK")
    with zipfile.ZipFile(docx) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "Матанализ" in xml
        assert "Производная" in xml