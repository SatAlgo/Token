"""Insert a starter menu the first time the app runs (idempotent)."""
from __future__ import annotations

from sqlmodel import Session, select

from .database import engine
from .models import MenuItem

STARTER_MENU = [
    ("Cutting Chai", "Strong half-glass classic", 1000, "Tea", "🍵"),
    ("Masala Chai", "Spiced with ginger & cardamom", 1500, "Tea", "🫖"),
    ("Green Tea", "Light and refreshing", 2000, "Tea", "🍃"),
    ("Filter Coffee", "South-Indian style", 2500, "Coffee", "☕"),
    ("Cold Coffee", "Iced, blended, frothy", 6000, "Coffee", "🧋"),
    ("Samosa", "Crispy potato samosa (2 pcs)", 3000, "Snacks", "🥟"),
    ("Veg Sandwich", "Grilled with mint chutney", 5000, "Snacks", "🥪"),
    ("Bun Maska", "Soft bun with butter", 2500, "Snacks", "🧈"),
]


def seed_menu() -> None:
    with Session(engine) as session:
        existing = session.exec(select(MenuItem)).first()
        if existing:
            return
        for name, desc, price, cat, emoji in STARTER_MENU:
            session.add(
                MenuItem(
                    name=name,
                    description=desc,
                    price_paise=price,
                    category=cat,
                    emoji=emoji,
                )
            )
        session.commit()
