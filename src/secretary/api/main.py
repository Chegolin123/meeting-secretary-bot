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


@app.get("/api/orders/{order_id}/export")
async def export_order(order_id: int):
    """Экспорт заказа в .docx (кабинет v1.1.0+)."""
    row = await _storage.get_order(order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="order not found")
    if row["status"] != "done":
        raise HTTPException(status_code=409, detail="заказ ещё не готов")
    from urllib.parse import quote  # noqa: PLC0415

    from fastapi.responses import Response  # noqa: PLC0415

    from secretary.team import build_export_docx  # noqa: PLC0415

    enriched = Storage.row_to_order(row)
    docx = build_export_docx(enriched)
    filename = f"созвон-{order_id}.docx"
    return Response(
        content=docx.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="sovon-{order_id}.docx"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")