"""v1.2.0 «Секретарь команды»: групповая логика — владелец заказа, дайджест, экспорт.

В группе/канале/супергруппе, куда добавлен бот, ВСЕ звонки принадлежат клиенту-чату:
лимит пакета и история считаются по chat.id; отчёт уходит в чат автоматически
(pipeline шлёт в order.tg_user_id = chat_id).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

TEAM_CHAT_TYPES = {"group", "supergroup", "channel"}


def resolve_owner(chat_type: str, user_id: int, chat_id: int) -> int:
    """Кому принадлежит заказ: для командных чатов — самому чату, иначе — пользователю."""
    if chat_type in TEAM_CHAT_TYPES:
        return chat_id
    return user_id


def render_digest(orders: list[dict], days: int = 7) -> str:
    """Недельный дайджест команды: N созвонов, минуты, топ-темы, последние заказы."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [o for o in orders if o.get("status") == "done" and _parse_dt(o.get("created_at")) >= cutoff]
    if not recent:
        return f"📊 За последние {days} дней созвонов не было."
    total_sec = sum(float(o.get("audio_duration_sec") or 0) for o in recent)
    topic_counter: dict[str, int] = {}
    for o in recent:
        summary = o.get("summary") or {}
        for topic in summary.get("key_topics", [])[:3]:
            topic_counter[str(topic)] = topic_counter.get(str(topic), 0) + 1
    top_topics = ", ".join(f"{t}×{c}" for t, c in sorted(topic_counter.items(), key=lambda x: -x[1])[:6])
    lines = [
        f"📊 <b>Дайджест команды за {days} дней</b>",
        f"Созвонов: <b>{len(recent)}</b> · Времени: <b>{int(total_sec // 60)} мин</b>",
    ]
    if top_topics:
        lines.append(f"Темы: {top_topics}")
    lines.append("")
    for o in recent[-8:]:
        created = (o.get("created_at") or "")[:16].replace("T", " ")
        lines.append(f"#{o['id']} · {created} · {int(float(o.get('audio_duration_sec') or 0)) // 60} мин")
    return "\n".join(lines)


def build_export_docx(order_row: dict) -> BytesIO:
    """Экспорт заказа в .docx из сохранённых данных (кабинет, v1.1.0+)."""
    from secretary.llm.deepseek import MeetingSummary  # noqa: PLC0415
    from secretary.report.formats import render_docx  # noqa: PLC0415
    from secretary.stt.base import TranscriptResult  # noqa: PLC0415

    summary_data = order_row.get("summary") or {
        "summary": "",
        "decisions": [],
        "tasks": [],
        "key_topics": [],
    }
    summary = MeetingSummary(
        summary=summary_data.get("summary", ""),
        decisions=[str(x) for x in summary_data.get("decisions", [])],
        tasks=[dict(t) for t in summary_data.get("tasks", [])],
        key_topics=[str(x) for x in summary_data.get("key_topics", [])],
    )
    result = TranscriptResult(
        text=order_row.get("transcript") or "",
        audio_duration_sec=float(order_row.get("audio_duration_sec") or 0),
        provider=order_row.get("provider") or "",
    )
    return render_docx(result, summary, order_id=int(order_row["id"]))


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)