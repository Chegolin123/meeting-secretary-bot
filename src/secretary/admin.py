"""Админ-версия бота (владелец): статистика, клиенты, заказы, ошибки, выдача пакетов.

Доступ — по TG id из ADMIN_TG_IDS (.env, через запятую). Команды:
/admin            — обзор: клиенты, заказы, минуты, ошибки
/admin clients    — клиенты: tg_id · пакет · использовано/лимит
/admin orders     — последние 10 заказов всех клиентов
/admin errors     — последние ошибки
/admin grant <id> <mini|pro> — выдать пакет вручную
/admin health     — провайдер STT, лимит файла
"""

from __future__ import annotations

from secretary.payments.gateway import Package


def is_admin(admin_ids_raw: str, user_id: int | str) -> bool:
    """Проверка владельца: ADMIN_TG_IDS='420000,500000' → только эти id."""
    if not admin_ids_raw:
        return False
    try:
        ids = {int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()}
    except ValueError:
        return False
    return int(user_id) in ids


def parse_grant(text: str) -> tuple[int, Package] | None:
    """'/admin grant 123456 mini' → (123456, Package.MINI). Некорректно — None."""
    try:
        user_id = int(text.split()[-2])
        name = text.split()[-1].lower()
    except (ValueError, IndexError):
        return None
    pkg = {p.value: p for p in Package}.get(name)
    if pkg is None or pkg is Package.STARTER:
        return None
    return user_id, pkg


def render_stats(clients: list[dict], orders: list[dict], provider: str, max_file_mb: int) -> str:
    """Общий отчёт /admin (HTML для Telegram)."""
    total_clients = len(clients)
    done = [o for o in orders if o["status"] == "done"]
    errors = [o for o in orders if o["status"] == "error"]
    total_min = sum(float(o.get("audio_duration_sec") or 0) for o in done) / 60
    lines = [
        "<b>🛠 Админ-панель</b>",
        f"Клиентов: <b>{total_clients}</b> · Заказов: <b>{len(orders)}</b> "
        f"(готово {len(done)}, ошибок {len(errors)})",
        f"Распознано времени: <b>{int(total_min)} мин</b>",
        f"STT: {provider} · файл до {max_file_mb} МБ",
        "",
        "<i>Команды: /admin clients · /admin orders · /admin errors · "
        "/admin grant &lt;id&gt; &lt;mini|pro&gt; · /admin health</i>",
    ]
    return "\n".join(lines)


def render_clients(clients: list[dict], packages: dict[int, dict]) -> str:
    lines = ["<b>👥 Клиенты</b>"]
    if not clients:
        return "\n".join(lines + ["Пока никто не регистрировался."])
    for c in clients:
        pkg = packages.get(c["package_id"]) or {}
        calls = pkg.get("calls_per_month", 0)
        used = c.get("used_calls", 0)
        lines.append(
            f"• <code>{c['tg_user_id']}</code> · {pkg.get('name', '?')} · {used}/{calls} зв · "
            f"создан {c['created_at'][:10]}"
        )
    return "\n".join(lines)


def render_orders(orders: list[dict]) -> str:
    lines = ["<b>📦 Заказы</b>"]
    if not orders:
        return "\n".join(lines + ["Пусто."])
    for o in orders[:10]:
        ts = (o.get("created_at") or "")[:16].replace("T", " ")
        err = f" — {o['error'][:60]}" if o.get("error") else ""
        lines.append(f"#{o['id']} · <code>{o['tg_user_id']}</code> · {o['status']} · {ts}{err}")
    return "\n".join(lines)


def render_errors(orders: list[dict]) -> str:
    lines = ["<b>🚨 Ошибки</b>"]
    errs = [o for o in orders if o["status"] == "error"]
    if not errs:
        return "\n".join(lines + ["Чисто! Ошибок нет."])
    for o in errs[:8]:
        lines.append(f"#{o['id']} · <code>{o['tg_user_id']}</code> · {o.get('error', '?')[:120]}")
    return "\n".join(lines)