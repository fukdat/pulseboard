"""Tests for the analytics engine using a small, hand-verified dataset."""

from __future__ import annotations

from datetime import date

from app.analytics import engine
from app.domain.models import Order, OrderLine, Product


def _order(oid: str, cust: str, d: str, amount_cents: int, sku: str = "SKU-A") -> Order:
    return Order(
        id=oid,
        customer_id=cust,
        ordered_at=date.fromisoformat(d),
        lines=(OrderLine(sku=sku, quantity=1, unit_price_cents=amount_cents),),
    )


# Alice: Jan + Feb + Mar (loyal). Bob: Jan only. Carol: Feb only.
ORDERS = [
    _order("o1", "alice", "2026-01-10", 1000),
    _order("o2", "bob", "2026-01-15", 2000),
    _order("o3", "alice", "2026-02-10", 1500),
    _order("o4", "carol", "2026-02-20", 3000),
    _order("o5", "alice", "2026-03-05", 500),
]


def test_revenue_by_month() -> None:
    rows = engine.revenue_by_period(ORDERS, "month")
    assert [(r.period, r.revenue_cents, r.order_count) for r in rows] == [
        ("2026-01", 3000, 2),
        ("2026-02", 4500, 2),
        ("2026-03", 500, 1),
    ]
    assert rows[0].aov_cents == 1500


def test_repeat_purchase_rate() -> None:
    # Only alice has >1 order, out of 3 customers.
    assert engine.repeat_purchase_rate(ORDERS) == 1 / 3


def test_customer_ltv_ordering_and_totals() -> None:
    ltvs = engine.customer_ltv(ORDERS)
    by_id = {c.customer_id: c for c in ltvs}
    assert by_id["alice"].total_cents == 3000
    assert by_id["alice"].order_count == 3
    assert by_id["bob"].total_cents == 2000
    assert ltvs[0].customer_id == "alice"  # sorted by spend desc
    assert engine.average_ltv_cents(ORDERS) == (3000 + 2000 + 3000) // 3


def test_cohort_retention() -> None:
    rows = engine.cohort_retention(ORDERS)
    cohorts = {r.cohort: r for r in rows}
    jan = cohorts["2026-01"]
    # Jan cohort = alice, bob (size 2). Offsets 0,1,2 (data ends in March).
    assert jan.size == 2
    assert jan.retention[0] == 1.0
    assert jan.retention[1] == 0.5  # only alice active in Feb
    assert jan.retention[2] == 0.5  # only alice active in Mar
    feb = cohorts["2026-02"]
    assert feb.size == 1  # carol
    assert feb.retention[0] == 1.0


def test_churn_rate() -> None:
    # As of Mar 31, window 30 days: customers with last order before Mar 1
    # are churned. bob (Jan) and carol (Feb 20) churned; alice active.
    rate = engine.churn_rate(ORDERS, as_of=date(2026, 3, 31), window_days=30)
    assert rate == 2 / 3


def test_top_products() -> None:
    orders = [
        _order("a", "x", "2026-01-01", 1000, sku="SKU-A"),
        _order("b", "y", "2026-01-02", 5000, sku="SKU-B"),
        _order("c", "z", "2026-01-03", 1000, sku="SKU-A"),
    ]
    top = engine.top_products(orders, limit=2)
    assert top[0].sku == "SKU-B"
    assert top[0].revenue_cents == 5000
    assert top[1].sku == "SKU-A"
    assert top[1].quantity == 2


def test_low_stock_alerts_sorted_by_urgency() -> None:
    products = [
        Product("A", "A", stock_on_hand=100, reorder_point=10),  # ok
        Product("B", "B", stock_on_hand=5, reorder_point=20),  # -15
        Product("C", "C", stock_on_hand=18, reorder_point=20),  # -2
    ]
    alerts = engine.low_stock_alerts(products)
    assert [p.sku for p in alerts] == ["B", "C"]


def test_kpi_summary() -> None:
    summary = engine.kpi_summary(ORDERS, as_of=date(2026, 3, 31), window_days=30)
    assert summary.total_revenue_cents == 8000
    assert summary.total_orders == 5
    assert summary.unique_customers == 3
    assert summary.aov_cents == 1600


def test_empty_inputs_are_safe() -> None:
    assert engine.revenue_by_period([]) == []
    assert engine.cohort_retention([]) == []
    assert engine.repeat_purchase_rate([]) == 0.0
    assert engine.churn_rate([]) == 0.0
    assert engine.kpi_summary([]).total_orders == 0
