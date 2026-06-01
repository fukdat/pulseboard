"""Tests for the CSV loaders."""

from __future__ import annotations

from datetime import date

from app.etl.csv_loader import load_inventory, load_orders

ORDERS_CSV = """order_id,customer_id,ordered_at,sku,quantity,unit_price_cents
o1,alice,2026-01-10,SKU-A,2,1000
o1,alice,2026-01-10,SKU-B,1,500
o2,bob,2026-01-12,SKU-A,1,1000
"""


def test_load_orders_groups_lines() -> None:
    result = load_orders(ORDERS_CSV)
    assert result.errors == []
    orders = {o.id: o for o in result.orders}
    assert len(orders) == 2
    assert len(orders["o1"].lines) == 2
    assert orders["o1"].total_cents == 2 * 1000 + 1 * 500
    assert orders["o1"].ordered_at == date(2026, 1, 10)


def test_load_orders_is_idempotent_on_duplicate_lines() -> None:
    doubled = ORDERS_CSV + "o1,alice,2026-01-10,SKU-A,2,1000\n"
    result = load_orders(doubled)
    orders = {o.id: o for o in result.orders}
    assert len(orders["o1"].lines) == 2  # duplicate (o1, SKU-A) ignored


def test_load_orders_collects_row_errors() -> None:
    bad = """order_id,customer_id,ordered_at,sku,quantity,unit_price_cents
o1,alice,2026-01-10,SKU-A,0,1000
o2,bob,not-a-date,SKU-A,1,1000
o3,carol,2026-01-12,SKU-A,1,1000
"""
    result = load_orders(bad)
    assert len(result.errors) == 2
    assert len(result.orders) == 1  # only o3 is valid


def test_load_orders_rejects_missing_columns() -> None:
    try:
        load_orders("order_id,customer_id\no1,alice")
    except ValueError as exc:
        assert "missing columns" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_load_inventory() -> None:
    csv_text = """sku,name,stock_on_hand,reorder_point
SKU-A,Widget,5,10
SKU-B,Gadget,100,20
"""
    products = {p.sku: p for p in load_inventory(csv_text)}
    assert products["SKU-A"].needs_reorder is True
    assert products["SKU-B"].needs_reorder is False
