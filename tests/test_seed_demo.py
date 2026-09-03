"""Тест демо-сидинга: наполнение кабинета без ключей (реальный main())."""

import pytest
from scripts.seed_demo import main as seed_main


@pytest.fixture
async def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from secretary.config import get_settings

    get_settings.cache_clear()
    await seed_main()
    from secretary.storage import Storage

    return Storage(str(tmp_path / "demo.db"))


async def test_seed_creates_orders(seeded):
    await seeded.init()
    rows = await seeded.list_orders(limit=5)
    assert len(rows) == 3
    assert sum(1 for r in rows if r["status"] == "done") == 2
    assert sum(1 for r in rows if r["status"] == "error") == 1
    done = [r for r in rows if r["status"] == "done"]
    assert any("лендинг" in r["summary_json"] for r in done)  # юрфирма-кейс в демо


async def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "d2.db"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data2"))
    from secretary.config import get_settings

    get_settings.cache_clear()
    await seed_main()
    await seed_main()  # повторный запуск не должен дублировать
    from secretary.storage import Storage

    s = Storage(str(tmp_path / "d2.db"))
    await s.init()
    rows = await s.list_orders(limit=10)
    assert len(rows) == 3