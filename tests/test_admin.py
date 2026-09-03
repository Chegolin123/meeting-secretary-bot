"""Тесты админ-панели: доступ, grant, отчёты."""

from secretary.admin import is_admin, parse_grant, render_clients, render_errors, render_stats
from secretary.payments.gateway import Package


def test_is_admin():
    assert is_admin("424242,555", 424242) is True
    assert is_admin("424242,555", 555) is True
    assert is_admin("424242", 999) is False
    assert is_admin("", 424242) is False
    assert is_admin("abc", 424242) is False


def test_parse_grant():
    assert parse_grant("/admin grant 123456 mini") == (123456, Package.MINI)
    assert parse_grant("/admin grant 123456 PRO") == (123456, Package.PRO)
    assert parse_grant("/admin grant 123456 starter") is None
    assert parse_grant("/admin grant 123456") is None
    assert parse_grant("много слов тут") is None


def test_render_stats_groups():
    clients = [{"tg_user_id": 1}, {"tg_user_id": 2}]
    orders = [
        {"id": 1, "status": "done", "audio_duration_sec": 1800.0, "tg_user_id": 1},
        {"id": 2, "status": "error", "tg_user_id": 1},
    ]
    text = render_stats(clients, orders, "assemblyai", 20)
    assert "Клиентов: <b>2</b>" in text
    assert "готово 1, ошибок 1" in text
    assert "30 мин" in text
    assert "assemblyai" in text


def test_render_clients_with_packages():
    clients = [{"tg_user_id": 111, "package_id": 2, "used_calls": 4, "created_at": "2026-09-03T00:00:00+00:00"}]
    packages = {2: {"name": "mini", "calls_per_month": 10}}
    text = render_clients(clients, packages)
    assert "111" in text
    assert "4/10" in text


def test_render_errors_clean():
    assert "Ошибок нет" in render_errors([])