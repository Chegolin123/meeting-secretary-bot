"""FastAPI: health + история заказов + мини-кабинет (фундамент v2.0.0).

v2.0.0: здесь вырастет self-service — оплата, лимиты по пакетам, экспорт.
Сейчас: JSON-API для кабинета и /health для мониторинга с NL VPS.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from secretary.config import get_settings
from secretary.storage import Storage

app = FastAPI(title="Secretary API", version="1.0.0")

_settings = get_settings()
_storage = Storage(_settings.db_path)

STATIC_DIR = Path(__file__).resolve().parents[3] / "web"


@app.on_event("startup")
async def _startup() -> None:
    await _storage.init()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "provider": _settings.stt_provider, "max_file_mb": _settings.max_file_mb}


@app.get("/api/orders")
async def list_orders(tg_user_id: int | None = None, limit: int = 50) -> list[dict]:
    rows = await _storage.list_orders(tg_user_id=tg_user_id, limit=min(limit, 200))
    return [Storage.row_to_order(r) for r in rows]


@app.get("/api/orders/{order_id}")
async def get_order(order_id: int) -> dict:
    row = await _storage.get_order(order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    return Storage.row_to_order(row)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")