"""In-memory dataset store with a deterministic demo seed.

In production this is replaced by a warehouse (Postgres/BigQuery) behind the
same accessor methods; the analytics engine is agnostic to the source.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from app.domain.models import Order, OrderLine, Product


class DatasetStore:
    """Holds the current orders and inventory for analysis."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._products: dict[str, Product] = {}

    def add_orders(self, orders: list[Order]) -> int:
        """Upsert orders by id (idempotent). Returns the count added/updated."""
        for order in orders:
            self._orders[order.id] = order
        return len(orders)

    def set_inventory(self, products: list[Product]) -> None:
        self._products = {p.sku: p for p in products}

    @property
    def orders(self) -> list[Order]:
        return list(self._orders.values())

    @property
    def products(self) -> list[Product]:
        return list(self._products.values())

    def clear(self) -> None:
        self._orders.clear()
        self._products.clear()


_CATALOG = [
    ("SKU-TSHIRT", "Cotton T-Shirt", 2_500),
    ("SKU-MUG", "Ceramic Mug", 1_200),
    ("SKU-CAP", "Baseball Cap", 1_800),
    ("SKU-BOTTLE", "Steel Bottle", 3_200),
    ("SKU-TOTE", "Canvas Tote", 1_500),
]


def build_demo_store(seed: int = 42) -> DatasetStore:
    """Build a reproducible demo dataset spanning six months."""
    rng = random.Random(seed)
    store = DatasetStore()

    start = date(2025, 11, 1)
    orders: list[Order] = []
    order_seq = 0

    # 60 customers; some are loyal repeat buyers, some churn after month one.
    for customer_index in range(60):
        customer_id = f"cust_{customer_index:03d}"
        loyal = customer_index % 3 == 0
        order_count = rng.randint(2, 6) if loyal else rng.randint(1, 2)
        first_offset = rng.randint(0, 90)
        for n in range(order_count):
            gap = rng.randint(15, 45)
            ordered_at = start + timedelta(days=first_offset + n * gap)
            if ordered_at > date(2026, 4, 30):
                break
            line_count = rng.randint(1, 3)
            lines = tuple(
                OrderLine(
                    sku=_CATALOG[rng.randrange(len(_CATALOG))][0],
                    quantity=rng.randint(1, 3),
                    unit_price_cents=_CATALOG[rng.randrange(len(_CATALOG))][2],
                )
                for _ in range(line_count)
            )
            order_seq += 1
            orders.append(
                Order(
                    id=f"ord_{order_seq:05d}",
                    customer_id=customer_id,
                    ordered_at=ordered_at,
                    lines=lines,
                )
            )

    store.add_orders(orders)
    store.set_inventory(
        [
            Product("SKU-TSHIRT", "Cotton T-Shirt", stock_on_hand=120, reorder_point=40),
            Product("SKU-MUG", "Ceramic Mug", stock_on_hand=8, reorder_point=25),
            Product("SKU-CAP", "Baseball Cap", stock_on_hand=15, reorder_point=20),
            Product("SKU-BOTTLE", "Steel Bottle", stock_on_hand=60, reorder_point=30),
            Product("SKU-TOTE", "Canvas Tote", stock_on_hand=5, reorder_point=15),
        ]
    )
    return store
