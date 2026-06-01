"""Pure, deterministic analytics over orders and inventory.

Every function is side-effect free: the same inputs always produce the same
outputs, which makes the whole engine trivially testable. Money is in cents.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.domain.models import Order, Product

Granularity = Literal["day", "month"]


@dataclass(frozen=True, slots=True)
class PeriodRevenue:
    period: str
    revenue_cents: int
    order_count: int
    aov_cents: int


@dataclass(frozen=True, slots=True)
class PeriodCustomers:
    period: str
    new_customers: int
    returning_customers: int


@dataclass(frozen=True, slots=True)
class CohortRow:
    cohort: str
    size: int
    retention: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CustomerLtv:
    customer_id: str
    order_count: int
    total_cents: int
    first_order: date
    last_order: date


@dataclass(frozen=True, slots=True)
class TopProduct:
    sku: str
    quantity: int
    revenue_cents: int


@dataclass(frozen=True, slots=True)
class KpiSummary:
    total_revenue_cents: int
    total_orders: int
    unique_customers: int
    aov_cents: int
    repeat_purchase_rate: float
    average_ltv_cents: int
    churn_rate: float


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


def _period_key(d: date, granularity: Granularity) -> str:
    return d.isoformat() if granularity == "day" else _month_key(d)


def revenue_by_period(
    orders: list[Order], granularity: Granularity = "month"
) -> list[PeriodRevenue]:
    """Revenue, order count and average order value per period."""
    revenue: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for order in orders:
        key = _period_key(order.ordered_at, granularity)
        revenue[key] += order.total_cents
        counts[key] += 1
    return [
        PeriodRevenue(
            period=key,
            revenue_cents=revenue[key],
            order_count=counts[key],
            aov_cents=revenue[key] // counts[key] if counts[key] else 0,
        )
        for key in sorted(revenue)
    ]


def _first_order_month(orders: list[Order]) -> dict[str, int]:
    first: dict[str, int] = {}
    for order in orders:
        idx = _month_index(order.ordered_at)
        cur = first.get(order.customer_id)
        if cur is None or idx < cur:
            first[order.customer_id] = idx
    return first


def customers_by_period(orders: list[Order]) -> list[PeriodCustomers]:
    """New vs returning active customers per month."""
    first_month = _first_order_month(orders)
    active: dict[str, set[str]] = defaultdict(set)
    for order in orders:
        active[_month_key(order.ordered_at)].add(order.customer_id)

    rows: list[PeriodCustomers] = []
    for period in sorted(active):
        # Reconstruct the month index from the key to compare cohorts.
        year, month = (int(part) for part in period.split("-"))
        period_index = year * 12 + (month - 1)
        customers = active[period]
        new = sum(1 for c in customers if first_month[c] == period_index)
        rows.append(
            PeriodCustomers(
                period=period,
                new_customers=new,
                returning_customers=len(customers) - new,
            )
        )
    return rows


def cohort_retention(orders: list[Order]) -> list[CohortRow]:
    """Monthly cohort retention: rows are first-order months, columns are
    months-since-acquisition, values are the share of the cohort still active.
    """
    if not orders:
        return []

    first_month = _first_order_month(orders)
    active_months: dict[str, set[int]] = defaultdict(set)
    for order in orders:
        active_months[order.customer_id].add(_month_index(order.ordered_at))

    cohorts: dict[int, list[str]] = defaultdict(list)
    for customer, cohort_index in first_month.items():
        cohorts[cohort_index].append(customer)

    last_month = max(_month_index(o.ordered_at) for o in orders)
    rows: list[CohortRow] = []
    for cohort_index in sorted(cohorts):
        members = cohorts[cohort_index]
        size = len(members)
        span = last_month - cohort_index
        retention = tuple(
            sum(1 for c in members if (cohort_index + offset) in active_months[c]) / size
            for offset in range(span + 1)
        )
        rows.append(
            CohortRow(cohort=f"{cohort_index // 12:04d}-{cohort_index % 12 + 1:02d}", size=size, retention=retention)
        )
    return rows


def customer_ltv(orders: list[Order]) -> list[CustomerLtv]:
    """Per-customer lifetime value, sorted by total spend descending."""
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    first: dict[str, date] = {}
    last: dict[str, date] = {}
    for order in orders:
        cid = order.customer_id
        totals[cid] += order.total_cents
        counts[cid] += 1
        if cid not in first or order.ordered_at < first[cid]:
            first[cid] = order.ordered_at
        if cid not in last or order.ordered_at > last[cid]:
            last[cid] = order.ordered_at

    result = [
        CustomerLtv(
            customer_id=cid,
            order_count=counts[cid],
            total_cents=totals[cid],
            first_order=first[cid],
            last_order=last[cid],
        )
        for cid in totals
    ]
    result.sort(key=lambda c: c.total_cents, reverse=True)
    return result


def average_ltv_cents(orders: list[Order]) -> int:
    ltvs = customer_ltv(orders)
    if not ltvs:
        return 0
    return sum(c.total_cents for c in ltvs) // len(ltvs)


def repeat_purchase_rate(orders: list[Order]) -> float:
    """Share of customers with more than one order."""
    counts: dict[str, int] = defaultdict(int)
    for order in orders:
        counts[order.customer_id] += 1
    if not counts:
        return 0.0
    repeat = sum(1 for n in counts.values() if n > 1)
    return repeat / len(counts)


def churn_rate(
    orders: list[Order], as_of: date | None = None, window_days: int = 90
) -> float:
    """Fraction of acquired customers with no order in the trailing window."""
    if not orders:
        return 0.0
    reference = as_of if as_of is not None else max(o.ordered_at for o in orders)
    cutoff = reference - timedelta(days=window_days)

    last: dict[str, date] = {}
    for order in orders:
        if order.ordered_at > reference:
            continue
        cid = order.customer_id
        if cid not in last or order.ordered_at > last[cid]:
            last[cid] = order.ordered_at

    if not last:
        return 0.0
    churned = sum(1 for d in last.values() if d < cutoff)
    return churned / len(last)


def top_products(orders: list[Order], limit: int = 10) -> list[TopProduct]:
    """Best-selling SKUs by revenue."""
    quantity: dict[str, int] = defaultdict(int)
    revenue: dict[str, int] = defaultdict(int)
    for order in orders:
        for line in order.lines:
            quantity[line.sku] += line.quantity
            revenue[line.sku] += line.amount_cents
    products = [
        TopProduct(sku=sku, quantity=quantity[sku], revenue_cents=revenue[sku])
        for sku in revenue
    ]
    products.sort(key=lambda p: p.revenue_cents, reverse=True)
    return products[:limit]


def low_stock_alerts(products: list[Product]) -> list[Product]:
    """Products at or below their reorder point, most urgent first."""
    alerts = [p for p in products if p.needs_reorder]
    alerts.sort(key=lambda p: p.stock_on_hand - p.reorder_point)
    return alerts


def kpi_summary(
    orders: list[Order], as_of: date | None = None, window_days: int = 90
) -> KpiSummary:
    """Headline KPIs for the dashboard cockpit."""
    total_revenue = sum(o.total_cents for o in orders)
    total_orders = len(orders)
    customers = {o.customer_id for o in orders}
    return KpiSummary(
        total_revenue_cents=total_revenue,
        total_orders=total_orders,
        unique_customers=len(customers),
        aov_cents=total_revenue // total_orders if total_orders else 0,
        repeat_purchase_rate=repeat_purchase_rate(orders),
        average_ltv_cents=average_ltv_cents(orders),
        churn_rate=churn_rate(orders, as_of=as_of, window_days=window_days),
    )
