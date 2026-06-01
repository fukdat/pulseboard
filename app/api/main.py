"""FastAPI application: metrics API, CSV ingest, and the dashboard cockpit."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import engine
from app.api.store import DatasetStore, build_demo_store

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

store: DatasetStore = build_demo_store()

app = FastAPI(
    title="PulseBoard API",
    version="0.1.0",
    description="E-commerce analytics & KPI cockpit.",
)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _encode(value: Any) -> Any:
    """Convert dataclasses (and lists of them) to JSON-ready structures."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics/summary")
async def summary() -> JSONResponse:
    return JSONResponse(_encode(engine.kpi_summary(store.orders)))


@app.get("/metrics/revenue")
async def revenue(granularity: Literal["day", "month"] = "month") -> JSONResponse:
    return JSONResponse(_encode(engine.revenue_by_period(store.orders, granularity)))


@app.get("/metrics/customers")
async def customers() -> JSONResponse:
    return JSONResponse(_encode(engine.customers_by_period(store.orders)))


@app.get("/metrics/cohorts")
async def cohorts() -> JSONResponse:
    return JSONResponse(_encode(engine.cohort_retention(store.orders)))


@app.get("/metrics/ltv")
async def ltv(limit: int = 20) -> JSONResponse:
    return JSONResponse(_encode(engine.customer_ltv(store.orders)[:limit]))


@app.get("/metrics/top-products")
async def top_products(limit: int = 10) -> JSONResponse:
    return JSONResponse(_encode(engine.top_products(store.orders, limit)))


@app.get("/alerts/low-stock")
async def low_stock() -> JSONResponse:
    return JSONResponse(_encode(engine.low_stock_alerts(store.products)))


@app.post("/ingest/orders")
async def ingest_orders(file: UploadFile) -> JSONResponse:
    """Upload an order-lines CSV; orders are upserted idempotently by id."""
    from app.etl.csv_loader import load_orders

    raw = (await file.read()).decode("utf-8")
    result = load_orders(raw)
    added = store.add_orders(result.orders)
    return JSONResponse({"added": added, "errors": result.errors})
