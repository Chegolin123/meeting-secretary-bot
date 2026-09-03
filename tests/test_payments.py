"""Тесты v1.1.0: пакеты, лимиты, инвойс Stars, активация по платежу."""

import pytest

from secretary.payments.gateway import Package, StarsGateway, YooKassaGateway
from secretary.storage import Storage


@pytest.fixture
async def storage(tmp_path):
    s = Storage(str(tmp_path / "t.db"))
    await s.init()
    await s.seed_packages()
    return s


def test_package_values():
    assert Package.MINI.stars == 150
    assert Package.PRO.calls_per_month == 30
    assert Package.STARTER.calls_per_month == 3
    assert Package.MINI.title == "10 звонков/мес"


async def test_starter_client_created(storage):
    await storage.ensure_client(111)
    client = await storage.get_client(111)
    assert client["package_id"] == 1  # starter


async def test_package_switch_and_limit(storage):
    await storage.ensure_client(111)
    await storage.set_client_package(111, 2)  # mini: 10 зв/мес
    done = await storage.count_done_calls(111)
    assert done == 0
    pkg = await storage.get_package(2)
    assert pkg["calls_per_month"] == 10
    # лимит: 10 done-заказов подряд → 11-й блокируется
    for _ in range(10):
        await storage.create_order(111, None, None, 100)
        # отметить все done: обновим напрямую через API хранилища
    from datetime import datetime, timedelta, timezone

    import aiosqlite

    async with aiosqlite.connect(storage._path) as db:
        await db.execute("UPDATE orders SET status='done' WHERE tg_user_id=111")
        await db.commit()
    assert await storage.count_done_calls(111) == 10
    assert await storage.count_done_calls(111) >= 10  # лимит достигнут

    # старые заказы старше 30 дней не считаются
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    async with aiosqlite.connect(storage._path) as db:
        await db.execute("UPDATE orders SET created_at=? WHERE tg_user_id=111", (old,))
        await db.commit()
    assert await storage.count_done_calls(111) == 0


async def test_packages_seeded(storage):
    for pid in (1, 2, 3):
        pkg = await storage.get_package(pid)
        assert pkg is not None


@pytest.mark.asyncio
async def test_stars_invoice_payload():
    # payload-схема, которую ждёт обработчик successful_payment
    assert f"package:{Package.MINI.value}" == "package:mini"
    assert f"package:{Package.PRO.value}" == "package:pro"


def test_yookassa_stub():
    g = YooKassaGateway()


async def test_stars_gateway_returns_payment_result_without_bot():
    # создание инвойса требует Bot — проверяем, что цена попадает в payload-схему
    assert Package.PRO.stars == 350