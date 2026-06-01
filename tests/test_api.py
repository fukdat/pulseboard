"""End-to-end API tests using the seeded demo dataset."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_served() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "PulseBoard" in res.text


def test_summary_has_demo_data() -> None:
    body = client.get("/metrics/summary").json()
    assert body["total_orders"] > 0
    assert body["unique_customers"] > 0
    assert 0.0 <= body["repeat_purchase_rate"] <= 1.0
    assert 0.0 <= body["churn_rate"] <= 1.0


def test_revenue_and_cohorts_endpoints() -> None:
    revenue = client.get("/metrics/revenue?granularity=month").json()
    assert isinstance(revenue, list) and revenue
    assert {"period", "revenue_cents", "order_count", "aov_cents"} <= revenue[0].keys()

    cohorts = client.get("/metrics/cohorts").json()
    assert isinstance(cohorts, list) and cohorts
    assert cohorts[0]["retention"][0] == 1.0


def test_low_stock_endpoint() -> None:
    alerts = client.get("/alerts/low-stock").json()
    skus = {a["sku"] for a in alerts}
    assert "SKU-TOTE" in skus  # seeded at 5 / reorder 15


def test_ingest_orders_is_idempotent() -> None:
    csv_text = (
        "order_id,customer_id,ordered_at,sku,quantity,unit_price_cents\n"
        "ext_1,ext_cust,2026-05-01,SKU-NEW,1,9999\n"
    )
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}

    first = client.post("/ingest/orders", files=files).json()
    assert first["added"] == 1
    assert first["errors"] == []
    after_first = client.get("/metrics/summary").json()["total_orders"]

    # Re-uploading the same file must not duplicate the order.
    client.post("/ingest/orders", files=files)
    after_second = client.get("/metrics/summary").json()["total_orders"]
    assert after_first == after_second
