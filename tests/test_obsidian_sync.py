"""Тесты моста Obsidian: генерация заметки, роутинг (append/new/ask), идемпотентность."""

from pathlib import Path

from scripts.obsidian_sync import apply_decision, render_note, sync


def _done_order(order_id=1):
    return {
        "id": order_id,
        "tg_user_id": 743554312,
        "status": "done",
        "provider": "assemblyai",
        "audio_duration_sec": 1860.0,
        "created_at": "2026-09-03T19:00:00+00:00",
        "summary": {
            "summary": "Обсудили план.",
            "decisions": ["Стартуем"],
            "tasks": [{"task": "ТЗ", "owner": "Марина", "priority": "high"}],
            "key_topics": ["план", "сроки"],
        },
        "transcript": "[Спикер 1] Привет.\n[Спикер 2] Привет!",
    }


def test_render_note_has_sections():
    text = render_note(_done_order())
    assert "tags: [созвон, стенограмма]" in text
    assert "Саммари" in text and "Обсудили план." in text
    assert "✅ Решения" in text
    assert "🔴 ТЗ — Марина" in text
    assert "[Спикер 1] Привет." in text
    assert "ИИ-секретарь как услуга" in text


def test_apply_append_increases_existing_note(tmp_path):
    target = tmp_path / "01 — Проекты" / "Proj.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Проект\n\nтекст", encoding="utf-8")
    mode, path = apply_decision(
        {"mode": "append", "target_path": "01 — Проекты/Proj.md", "confidence": 0.9},
        _done_order(5),
        tmp_path,
    )
    assert mode == "append"
    assert "Созвон #5" in target.read_text(encoding="utf-8")
    assert "# Проект" in target.read_text(encoding="utf-8")


def test_apply_append_archive_rejected(tmp_path):
    target = tmp_path / "99 — Архив" / "Old.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Старое", encoding="utf-8")
    mode, path = apply_decision(
        {"mode": "append", "target_path": "99 — Архив/Old.md", "confidence": 0.9},
        _done_order(6),
        tmp_path,
    )
    assert mode == "ask"  # архив = только чтение
    assert "Созвон #6" not in target.read_text(encoding="utf-8")


def test_apply_new_creates_in_folder(tmp_path):
    mode, path = apply_decision(
        {"mode": "new", "folder": "05 — Идеи и планы", "note_name": "Новая тема созвона", "confidence": 0.8},
        _done_order(7),
        tmp_path,
    )
    assert mode == "new"
    assert path == tmp_path / "05 — Идеи и планы" / "Новая тема созвона.md"
    assert path.exists()


def test_apply_ask_creates_note_and_question(tmp_path):
    mode, path = apply_decision(
        {"mode": "ask", "reason": "личная тема, вариантов несколько", "confidence": 0.3},
        _done_order(8),
        tmp_path,
    )
    assert mode == "ask"
    assert "Созвоны" in str(path) and path.exists()
    q = tmp_path / "00 — Вход" / "Созвоны" / "_вопросы" / "Вопрос-созвон #8.md"
    assert "личная тема" in q.read_text(encoding="utf-8")


def test_sync_routes_and_maps(tmp_path, monkeypatch):
    import scripts.obsidian_sync as m

    class FakeResp:
        def json(self):
            return [_done_order(1), {**_done_order(2), "tg_user_id": 999}]

    monkeypatch.setattr(m.httpx, "get", lambda url, timeout=None: FakeResp())

    def fake_route(api, order, catalog):
        return {"mode": "new", "folder": "05 — Идеи и планы", "note_name": "Роут-тема", "confidence": 0.9, "reason": ""}

    monkeypatch.setattr(m, "fetch_route", fake_route)
    created, skipped, questions = sync("http://x", tmp_path, owner=743554312)
    assert created == 1
    assert questions == 0
    note = tmp_path / "05 — Идеи и планы" / "Роут-тема.md"
    assert note.exists()
    mapping = m.load_sync_map(tmp_path)
    assert mapping["1"].endswith("Роут-тема.md")

    # повторный прогон — skip по карте
    created2, skipped2, _ = sync("http://x", tmp_path, owner=743554312)
    assert created2 == 0 and skipped2 == 1