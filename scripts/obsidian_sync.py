"""Мост: саммари созвонов из API секретаря → заметки в Obsidian (только владелец).

Роутинг (v2): для каждого созвона DeepSeek на сервере решает, КУДА писать:
  - append — дополнить существующую заметку проекта/темы;
  - new — создать заметку в подходящей папке vault;
  - ask  — неуверен → заметка во «Входящие/Созвоны», а владельцу создаётся файл-ВОПРОС
           (НЕ додумываем: решение без явных оснований не принимается).

Мост не пишет в «99 — Архив» и не трогает чужие заказы (только владелец, ADMIN_TG_IDS).
Идемпотентность: карта .secretary_sync.json в корне vault (order_id → путь заметки).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

FALLBACK_DIR = "00 — Вход/Созвоны"
QUESTIONS_DIR = "00 — Вход/Созвоны/_вопросы"
EXCLUDED = {".obsidian", "Вложения", "99 — Архив", ".git"}
SYNC_MAP = ".secretary_sync.json"
LINK_IDEA = "[[Стенограммы созвонов — ИИ-секретарь как услуга]]"


def _fmt_dt(sec: float) -> str:
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ч {m:02d} мин"
    if m:
        return f"{m} мин {s:02d} с"
    return f"{s} с"


def render_note(order: dict) -> str:
    """Заметка Obsidian из обогащённого заказа (Storage.row_to_order)."""
    created = (order.get("created_at") or "")[:10]
    summary = order.get("summary") or {}
    lines = [
        "---",
        "tags: [созвон, стенограмма]",
        "тип: созвон",
        "статус: готово",
        f'создан: "{created}"',
        f'длительность: "{_fmt_dt(float(order.get("audio_duration_sec") or 0))}"',
        f'провайдер: {order.get("provider") or "—"}',
        'updated: "' + datetime.now(timezone.utc).strftime("%Y-%m-%d") + '"',
        "---",
        "",
        f"# 🎙 Созвон #{order['id']} — {created}",
        "",
        "## 📋 Саммари",
        "",
        str(summary.get("summary") or "—"),
        "",
    ]
    if summary.get("decisions"):
        lines += ["## ✅ Решения", ""]
        lines += [f"- {d}" for d in summary["decisions"]] + [""]
    if summary.get("tasks"):
        lines += ["## 🎯 Задачи", ""]
        for t in summary["tasks"]:
            prio = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(str(t.get("priority", "")).lower(), "⚪")
            owner = f" — {t.get('owner', '')}" if t.get("owner") else ""
            lines.append(f"- {prio} {t.get('task', '')}{owner}")
        lines.append("")
    if summary.get("key_topics"):
        lines += ["## 🏷 Темы", "", ", ".join(str(x) for x in summary["key_topics"]), ""]
    transcript = (order.get("transcript") or "").strip()
    if transcript:
        lines += ["## 📄 Стенограмма", "", transcript, ""]
    lines += ["## Связанные", "", f"- {LINK_IDEA}", "- [[MOC — Идеи]]", ""]
    return "\n".join(lines)


def note_path(vault: Path, order_id: int, created: str) -> Path:
    date = (created or "")[:10] or "no-date"
    return vault / FALLBACK_DIR / f"Созвон #{order_id} — {date}.md"


def question_path(vault: Path, order_id: int) -> Path:
    return vault / QUESTIONS_DIR / f"Вопрос-созвон #{order_id}.md"


def scan_catalog(vault: Path, limit: int = 150) -> list[dict[str, str]]:
    """Каталог vault для роутера: относительные пути .md (без исключённых папок)."""
    catalog: list[dict[str, str]] = []
    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault)
        parts = rel.parts
        if parts and parts[0] in EXCLUDED:
            continue
        catalog.append({"path": str(rel), "name": path.stem})
        if len(catalog) >= limit:
            break
    return catalog


def fetch_route(api_url: str, order: dict, catalog: list[dict[str, str]]) -> dict:
    """POST /api/route; при недоступности — режим «вопрос» (не угадываем)."""
    if httpx is None:  # pragma: no cover
        raise SystemExit("httpx не установлен")
    payload = {
        "order_id": int(order["id"]),
        "summary": order.get("summary") or {},
        "catalog": catalog,
    }
    r = httpx.post(f"{api_url.rstrip('/')}/api/route", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def apply_decision(decision: dict, order: dict, vault: Path) -> tuple[str, Path]:
    """Применяет решение роутера. Возвращает (mode, итоговый путь заметки)."""
    mode = decision.get("mode")
    if mode == "append":
        target = vault / str(decision.get("target_path", ""))
        if target.exists() and "99 — Архив" not in str(target):
            _append_to_note(target, order)
            return "append", target
        mode = "ask"  # целевая заметка пропала/в архиве — не додумываем
    if mode == "new":
        folder = str(decision.get("folder", "")).strip().strip("/")
        if folder == "99 — Архив":
            mode = "ask"
        if mode == "new":
            folder = folder or FALLBACK_DIR
            name = str(decision.get("note_name") or f"Созвон #{order['id']}").strip() or f"Созвон #{order['id']}"
            safe = "".join(c for c in name if c not in '\\/:*?"<>|')
            target_dir = vault / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{safe}.md"
            target.write_text(render_note(order), encoding="utf-8")
            return "new", target
    # ask (и любые fallback): пишем в Созвоны + файл-вопрос владельцу
    target = note_path(vault, int(order["id"]), order.get("created_at") or "")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(render_note(order), encoding="utf-8")
    q = question_path(vault, int(order["id"]))
    q.parent.mkdir(parents=True, exist_ok=True)
    reason = decision.get("reason") or "не указана"
    q.write_text(
        "---\ntags: [вопрос, созвон]\nтип: вопрос\nстатус: открыт\n---\n\n"
        f"# ❓ Куда сохранить созвон #{order['id']}?\n\n"
        f"Роутер не уверен: {reason}\n\n"
        f"Заметка временно: {target.relative_to(vault)}\n\n"
        "Варианты:\n"
        f"- {decision.get('note_name') or ''} ({decision.get('folder') or 'папка не указана'}) — если согласен, перенеси заметку\n"
        f"- {{другая заметка/папка из каталога — укажи здесь}}\n\n"
        "После переноса обнови карту .secretary_sync.json.",
        encoding="utf-8",
    )
    return "ask", target


def _append_to_note(target: Path, order: dict) -> None:
    created = (order.get("created_at") or "")[:10]
    summary = order.get("summary") or {}
    section = [
        "",
        "---",
        f"## 🎙 Созвон #{order['id']} — {created}",
        "",
        f"**Саммари:** {summary.get('summary') or '—'}",
    ]
    if summary.get("decisions"):
        section.append("")
        section += ["**Решения:**"] + [f"- {d}" for d in summary["decisions"]]
    if summary.get("tasks"):
        section.append("")
        section += ["**Задачи:**"] + [
            f"- {t.get('task', '')} — {t.get('owner', '')} [{t.get('priority', '')}]" for t in summary["tasks"]
        ]
    with target.open("a", encoding="utf-8") as f:
        f.write("\n".join(section) + "\n")


def load_sync_map(vault: Path) -> dict:
    p = vault / SYNC_MAP
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_sync_map(vault: Path, mapping: dict, order_id: int, path: str) -> None:
    mapping[str(order_id)] = str(path)
    (vault / SYNC_MAP).write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def sync(api_url: str, vault: Path, owner: int, limit: int = 100) -> tuple[int, int, int]:
    """Возвращает (создано, пропущено, вопросов)."""
    if httpx is None:  # pragma: no cover
        raise SystemExit("httpx не установлен — pip install httpx")
    orders = httpx.get(f"{api_url.rstrip('/')}/api/orders?limit={limit}", timeout=15).json()
    mapping = load_sync_map(vault)
    created = skipped = questions = 0
    for order in orders:
        oid = int(order["id"])
        if int(order.get("tg_user_id") or 0) != owner or order.get("status") != "done":
            continue
        if str(oid) in mapping and (vault / mapping[str(oid)]).exists():
            skipped += 1
            continue
        catalog = scan_catalog(vault)
        try:
            decision = fetch_route(api_url, order, catalog)
        except Exception as e:  # noqa: BLE001 — роутер недоступен → вопрос, не догадка
            decision = {"mode": "ask", "reason": f"роутер недоступен: {e}"}
        mode, target = apply_decision(decision, order, vault)
        save_sync_map(vault, mapping, oid, str(target.relative_to(vault)))
        if mode == "ask":
            questions += 1
        else:
            created += 1
        print(f"  → #{oid} [{mode}] {target.relative_to(vault)}")
    return created, skipped, questions


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Мост: созвоны → Obsidian (с LLM-роутингом)")
    p.add_argument("--api", default=os.environ.get("SECRETARY_API", "http://100.95.240.30:8000"))
    p.add_argument("--vault", default=r"C:\Users\Aleks\Desktop\opencode\obs")
    p.add_argument("--owner", type=int, default=None, help="TG id владельца (по умолчанию ADMIN_TG_IDS из .env)")
    p.add_argument("--interval", type=int, default=0, help="Цикл каждые N минут (0 = разово)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    owner = args.owner
    if owner is None:
        ids = os.environ.get("ADMIN_TG_IDS", "")
        owner = int(ids.split(",")[0]) if ids else 0
    while True:
        created, skipped, questions = sync(args.api, Path(args.vault), owner)
        print(f"[{time.strftime('%H:%M:%S')}] создано: {created} · пропущено: {skipped} · вопросов: {questions}")
        if args.interval <= 0:
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()