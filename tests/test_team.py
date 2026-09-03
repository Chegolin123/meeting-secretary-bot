"""Тесты v1.2.0 «Секретарь команды»: владелец заказа, дайджест, экспорт."""

import json
from datetime import datetime, timedelta, timezone

from secretary.team import build_export_docx, render_digest, resolve_owner


def test_resolve_owner_personal_chat():
    assert resolve_owner("private", user_id=111, chat_id=222) == 111


def test_resolve_owner_team_chat():
    for chat_type in ("group", "supergroup", "channel"):
        assert resolve_owner(chat_type, user_id=111, chat_id=-100123) == -100123


def test_render_digest_empty():
    text = render_digest([], days=7)
    assert "не было" in text


def test_render_digest_aggregates():
    now = datetime.now(timezone.utc).isoformat()

    def order(oid, sec, topics):
        return {
            "id": oid,
            "status": "done",
            "audio_duration_sec": sec,
            "created_at": now,
            "summary": {"key_topics": topics},  # контракт: обогащённая строка (Storage.row_to_order)
        }

    rows = [order(1, 600, ["сроки", "бюджет"]), order(2, 900, ["сроки"])]
    text = render_digest(rows, days=7)
    assert "2" in text.split("Созвонов:")[1].split("·")[0]  # N созвонов
    assert "25 мин" in text  # 600+900 сек = 25 мин
    assert "сроки" in text
    assert "бюджет" in text


def test_render_digest_skips_old_and_errors():
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    rows = [
        {"id": 1, "status": "done", "audio_duration_sec": 60, "created_at": old},
        {"id": 2, "status": "error", "audio_duration_sec": 0, "created_at": datetime.now(timezone.utc).isoformat()},
    ]
    text = render_digest(rows, days=7)
    assert "не было" in text


def test_build_export_docx_from_saved_row():
    row = {
        "id": 42,
        "status": "done",
        "provider": "assemblyai",
        "audio_duration_sec": 61.0,
        "summary_json": json.dumps(
            {"summary": "Итог", "decisions": ["Ок"], "tasks": [{"task": "Т", "owner": "А", "priority": "high"}], "key_topics": ["тема"]}
        ),
        "transcript": "[Спикер 1] привет",
    }
    import zipfile

    docx = build_export_docx(row)
    data = docx.getvalue()
    assert data.startswith(b"PK")
    with zipfile.ZipFile(docx) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "созвона #42" in xml or "42" in xml
        assert "Итог" in xml