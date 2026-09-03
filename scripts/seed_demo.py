"""Демо-данные для локального тестирования кабинета (без внешних ключей).

    .venv/Scripts/python scripts/seed_demo.py        # наполнит data/secretary.db
    .venv/Scripts/python -m uvicorn secretary.api.main:app --port 8011
    → http://127.0.0.1:8011
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from secretary.config import Settings
from secretary.storage import Storage

DEMO_ORDERS = [
    {
        "tg_user_id": 424242,
        "file_name": "demo-1",
        "mime": "audio/ogg",
        "size_bytes": 4_500_000,
        "status": "done",
        "provider": "assemblyai",
        "audio_duration_sec": 1860.0,  # 31 мин
        "summary": {
            "summary": "Обсудили запуск лендинга для юрфирмы: сроки, бюджет и распределение задач.",
            "decisions": ["Стартуем 10 сентября", "Подрядчик — текущий исполнитель", "Бюджет 45 000 ₽"],
            "tasks": [
                {"task": "Подготовить ТЗ на лендинг", "owner": "Марина", "priority": "high"},
                {"task": "Прогнать тексты через ИИ-секретаря", "owner": "Все", "priority": "medium"},
                {"task": "Забронировать домен", "owner": "Игорь", "priority": "low"},
            ],
            "key_topics": ["лендинг", "бюджет", "сроки"],
        },
        "transcript": (
            "[Спикер 1] Итак, по лендингу: какие сроки?\n"
            "[Спикер 2] Две недели, если ТЗ будет завтра.\n"
            "[Спикер 1] Бюджет не меняем, 45 тысяч.\n"
            "[Спикер 2] Договорились, стартуем десятого."
        ),
    },
    {
        "tg_user_id": 424242,
        "file_name": "demo-2",
        "mime": "video/mp4",
        "size_bytes": 120_000_000,
        "status": "done",
        "provider": "assemblyai",
        "audio_duration_sec": 720.0,  # 12 мин
        "summary": {
            "summary": "HR-интервью кандидата: опыт, ожидания по зарплате, следующие шаги.",
            "decisions": ["Пригласить на техническое интервью"],
            "tasks": [
                {"task": "Согласовать второе интервью", "owner": "Марина", "priority": "high"},
            ],
            "key_topics": ["интервью", "кандидат"],
        },
        "transcript": (
            "[Спикер 1] Расскажите про ваш опыт с Python.\n"
            "[Спикер 2] Три года, последний проект — аналитика для ритейла.\n"
            "[Спикер 1] Отлично, пригласим на второе интервью."
        ),
    },
    {
        "tg_user_id": 424242,
        "file_name": "demo-3",
        "mime": "audio/mp3",
        "size_bytes": 900_000,
        "status": "error",
        "provider": "assemblyai",
        "audio_duration_sec": 0.0,
        "error": "demo: слишком шумная запись",
        "summary": None,
        "transcript": None,
    },
]


async def main() -> None:
    settings = Settings()
    storage = Storage(settings.db_path)
    await storage.init()
    await storage.seed_packages()
    existing = await storage.list_orders(limit=1)
    if existing:
        print(f"БД уже содержит заказы ({len(existing)}+) — демо НЕ добавляю (сбрось: del data/secretary.db)")
        return
    for spec in DEMO_ORDERS:
        summary_json = json.dumps(spec["summary"], ensure_ascii=False) if spec["summary"] else None
        await storage.create_order(
            tg_user_id=spec["tg_user_id"],
            file_name=spec["file_name"],
            mime=spec["mime"],
            size_bytes=spec["size_bytes"],
        )
        order_id = (await storage.list_orders(tg_user_id=spec["tg_user_id"], limit=1))[0]["id"]
        if spec["status"] == "done":
            await storage.save_result(
                order_id,
                provider=spec["provider"],
                audio_duration_sec=spec["audio_duration_sec"],
                summary_json=summary_json,
                transcript=spec["transcript"],
            )
        else:
            await storage.set_status(order_id, "error", error=spec.get("error"))
        print(f"  # {order_id}: {spec['status']} · {spec['mime']}")
    print(f"Готово. БД: {settings.db_path} — запусти uvicorn и открой http://127.0.0.1:8011")


if __name__ == "__main__":
    asyncio.run(main())