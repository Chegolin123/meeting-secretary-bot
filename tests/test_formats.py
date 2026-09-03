"""Тесты: отчёты (TG HTML, .docx)."""

from secretary.llm.deepseek import MeetingSummary
from secretary.report.formats import render_docx, render_tg_html, render_txt
from secretary.stt.base import TranscriptResult, Utterance


def _result() -> TranscriptResult:
    return TranscriptResult(
        text="A: один\nB: два",
        utterances=[Utterance("1", "один"), Utterance("2", "два")],
        audio_duration_sec=125,
        provider="assemblyai",
    )


def _summary() -> MeetingSummary:
    return MeetingSummary(
        summary="Обсудили <b>план</b>",
        decisions=["Решение 1"],
        tasks=[{"task": "Задача", "owner": "Иван", "priority": "high"}],
        key_topics=["тема"],
    )


def test_tg_html_escapes_html_and_has_sections():
    html = render_tg_html(_result(), _summary(), order_id=7)
    assert "#7" in html
    assert "Обсудили &lt;b&gt;план&lt;/b&gt;" in html  # эскейп от инъекций
    assert "Саммари" in html and "Решения" in html and "Задачи" in html
    assert "Спикер 1" in html
    assert "дисклеймер" not in html  # дисклеймер — в <i>...</i>, проверяем иначе
    assert "ответственность клиента" in html


def test_txt_full_transcript():
    txt = render_txt(_result())
    assert "[Спикер 1] один" in txt
    assert "[Спикер 2] два" in txt


def test_txt_without_speakers():
    tr = TranscriptResult(text="просто текст", provider="assemblyai")
    assert render_txt(tr) == "просто текст"


def test_docx_render():
    import zipfile

    docx = render_docx(_result(), _summary(), order_id=3)
    data = docx.getvalue()
    assert data.startswith(b"PK")  # валидный zip/docx
    with zipfile.ZipFile(docx) as zf:
        names = zf.namelist()
        assert "word/document.xml" in names
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "Итоги созвона" in xml
        assert "Обсудили" in xml  # саммари попало в документ