"""Core domain models. Money is stored as integer cents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def amount_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    customer_id: str
    ordered_at: date
    lines: tuple[OrderLine, ...]

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


@dataclass(frozen=True, slots=True)
class Product:
    sku: str
    name: str
    stock_on_hand: int
    reorder_point: int

    @property
    def needs_reorder(self) -> bool:
        return self.stock_on_hand <= self.reorder_point
