"""Payment abstraction supporting two modes:

- "demo"     : no keys, no real money. A fake order id is created and payment is
               auto-verified. Perfect for local development and live demos.
- "razorpay" : real Razorpay Checkout (UPI/cards/wallets). Use Test Mode keys
               (free) to try the full flow without spending money.

Both modes expose the same two functions so the rest of the app doesn't care
which one is active.
"""
from __future__ import annotations

import hashlib
import hmac

from .config import settings

_razorpay_client = None


def _client():
    global _razorpay_client
    if _razorpay_client is None:
        import razorpay  # imported lazily so demo mode needs no razorpay setup

        _razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    return _razorpay_client


def create_provider_order(amount_paise: int, receipt: str) -> dict:
    """Returns data the frontend needs to start checkout."""
    if settings.razorpay_enabled:
        order = _client().order.create(
            {"amount": amount_paise, "currency": "INR", "receipt": receipt}
        )
        return {
            "mode": "razorpay",
            "key_id": settings.RAZORPAY_KEY_ID,
            "provider_order_id": order["id"],
            "amount_paise": amount_paise,
        }

    # Demo mode — synthesise an order id locally.
    return {
        "mode": "demo",
        "key_id": None,
        "provider_order_id": f"demo_order_{receipt}",
        "amount_paise": amount_paise,
    }


def verify_payment(
    *, provider_order_id: str, payment_id: str, signature: str
) -> bool:
    """Confirm the payment really happened and wasn't spoofed by the client."""
    if settings.razorpay_enabled:
        # Razorpay signs (order_id|payment_id) with your key secret. We recompute
        # it and compare — this is the official server-side verification.
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{provider_order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # Demo mode — any payment for a demo order is accepted.
    return provider_order_id.startswith("demo_order_")
