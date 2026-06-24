"""Central configuration, loaded once from environment variables / .env file.

Keeping all settings in one place makes the app easy to deploy: on Render you
just set the same variable names in the dashboard instead of a .env file.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # reads a .env file if present; ignored in production where real env vars exist


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "tea123")

    PAYMENT_MODE: str = os.getenv("PAYMENT_MODE", "demo").lower()  # "demo" | "razorpay"
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")

    SHOP_NAME: str = os.getenv("SHOP_NAME", "Vakratunda Misal")

    # --- Image hosting (Cloudinary, free tier) ---
    # Set these three to upload item images to Cloudinary. If they're empty the
    # app falls back to saving uploads locally under static/uploads/ so it still
    # runs with zero setup.
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./teashop.db")

    # A token is only valid for a few hours after issue (a tea doesn't take a day).
    TOKEN_TTL_MINUTES: int = int(os.getenv("TOKEN_TTL_MINUTES", "240"))

    @property
    def cloudinary_enabled(self) -> bool:
        return bool(
            self.CLOUDINARY_CLOUD_NAME
            and self.CLOUDINARY_API_KEY
            and self.CLOUDINARY_API_SECRET
        )

    @property
    def razorpay_enabled(self) -> bool:
        return (
            self.PAYMENT_MODE == "razorpay"
            and bool(self.RAZORPAY_KEY_ID)
            and bool(self.RAZORPAY_KEY_SECRET)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
