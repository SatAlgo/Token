"""Database tables, defined with SQLModel (SQLAlchemy + Pydantic in one).

Money is always stored as integer paise (1 rupee = 100 paise) to avoid floating
point rounding bugs — a classic mistake when handling currency.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"  # created, waiting for the customer to pay
    PAID = "paid"                        # paid -> a live token now exists
    SERVED = "served"                    # waiter delivered the order, token is dead
    CANCELLED = "cancelled"              # never paid / abandoned
    REFUNDED = "refunded"                # money returned


class MenuItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    price_paise: int                     # e.g. 1500 = ₹15.00
    category: str = "Tea"
    emoji: str = "🍵"
    image_url: str = ""                  # Cloudinary (or local) image; emoji is the fallback
    available: bool = True


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # Short human/url-friendly id shown on the token, e.g. "T-9F3A2".
    public_id: str = Field(index=True, unique=True)
    items_json: str                      # JSON: [{"id","name","qty","price_paise"}]
    total_paise: int
    table_number: str | None = None      # where to deliver the order (e.g. "5", "A2")
    status: OrderStatus = Field(default=OrderStatus.PENDING_PAYMENT, index=True)

    # Unique JWT id ("jti"). Lets us revoke a single token server-side when served.
    token_jti: str | None = Field(default=None, index=True)

    # Payment bookkeeping (Razorpay ids, or "demo" in demo mode).
    payment_provider: str | None = None
    payment_ref: str | None = None       # razorpay_payment_id
    provider_order_id: str | None = None # razorpay_order_id

    created_at: datetime = Field(default_factory=utcnow)
    paid_at: datetime | None = None
    served_at: datetime | None = None
