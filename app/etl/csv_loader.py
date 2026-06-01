"""CSV ingestion for orders and inventory.

Loaders are tolerant: malformed rows are collected as errors rather than
aborting the whole import, and identical order lines are de-duplicated so a
re-uploaded file is idempotent.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date

from app.domain.models import Order, OrderLine, Product


@dataclass(frozen=True, slots=True)
class LoadResult:
    orders: list[Order]
    errors: list[str]


_ORDER_FIELDS = {"order_id", "customer_id", "ordered_at", "sku", "quantity", "unit_price_cents"}
_INVENTORY_FIELDS = {"sku", "name", "stock_on_hand", "reorder_point"}


def _require_fields(reader: csv.DictReader[str], required: set[str], source: str) -> None:
    header = set(reader.fieldnames or [])
    missing = required - header
    if missing:
        raise ValueError(f"{source} is missing columns: {', '.join(sorted(missing))}")


def load_orders(csv_text: str) -> LoadResult:
    """Parse an order-lines CSV into grouped orders.

    Expected columns: order_id, customer_id, ordered_at (YYYY-MM-DD), sku,
    quantity, unit_price_cents. Rows are grouped into orders by order_id.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    _require_fields(reader, _ORDER_FIELDS, "orders CSV")

    grouped: dict[str, dict[str, object]] = {}
    seen_lines: set[tuple[str, str]] = set()
    errors: list[str] = []

    for line_no, row in enumerate(reader, start=2):
        try:
            order_id = row["order_id"].strip()
            customer_id = row["customer_id"].strip()
            sku = row["sku"].strip()
            if not order_id or not customer_id or not sku:
                raise ValueError("order_id, customer_id and sku are required")
            ordered_at = date.fromisoformat(row["ordered_at"].strip())
            quantity = int(row["quantity"])
            unit_price_cents = int(row["unit_price_cents"])
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            if unit_price_cents < 0:
                raise ValueError("unit_price_cents must be non-negative")
        except (ValueError, KeyError) as exc:
            errors.append(f"row {line_no}: {exc}")
            continue

        dedup_key = (order_id, sku)
        if dedup_key in seen_lines:
            continue
        seen_lines.add(dedup_key)

        entry = grouped.setdefault(
            order_id,
            {"customer_id": customer_id, "ordered_at": ordered_at, "lines": []},
        )
        lines = entry["lines"]
        assert isinstance(lines, list)
        lines.append(OrderLine(sku=sku, quantity=quantity, unit_price_cents=unit_price_cents))

    orders: list[Order] = []
    for order_id, entry in grouped.items():
        customer_id = entry["customer_id"]
        ordered_at_value = entry["ordered_at"]
        lines = entry["lines"]
        assert isinstance(customer_id, str)
        assert isinstance(ordered_at_value, date)
        assert isinstance(lines, list)
        orders.append(
            Order(
                id=order_id,
                customer_id=customer_id,
                ordered_at=ordered_at_value,
                lines=tuple(lines),
            )
        )
    orders.sort(key=lambda o: o.ordered_at)
    return LoadResult(orders=orders, errors=errors)


def load_inventory(csv_text: str) -> list[Product]:
    """Parse an inventory CSV. Columns: sku, name, stock_on_hand, reorder_point."""
    reader = csv.DictReader(io.StringIO(csv_text))
    _require_fields(reader, _INVENTORY_FIELDS, "inventory CSV")

    products: list[Product] = []
    for row in reader:
        sku = row["sku"].strip()
        if not sku:
            continue
        products.append(
            Product(
                sku=sku,
                name=row["name"].strip(),
                stock_on_hand=int(row["stock_on_hand"]),
                reorder_point=int(row["reorder_point"]),
            )
        )
    return products
