"""Image upload helper.

If Cloudinary credentials are configured we upload there and return the hosted
HTTPS URL. Otherwise we fall back to saving the file under static/uploads/ so the
app keeps working with zero setup. Either way the caller gets back a URL string.
"""
from __future__ import annotations

import io
import os
import secrets

from .config import settings

UPLOAD_DIR = "static/uploads"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

_cloudinary_configured = False


def _ensure_cloudinary():
    global _cloudinary_configured
    if not _cloudinary_configured:
        import cloudinary

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        _cloudinary_configured = True


def upload_image(data: bytes, filename: str) -> str | None:
    """Returns a URL for the stored image, or None if no data was provided."""
    if not data:
        return None

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"

    if settings.cloudinary_enabled:
        import cloudinary.uploader

        _ensure_cloudinary()
        result = cloudinary.uploader.upload(
            io.BytesIO(data),
            folder="teashop",
            resource_type="image",
            transformation=[{"width": 600, "height": 600, "crop": "limit"}],
        )
        return result["secure_url"]

    # Local fallback — served by the existing /static mount.
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = secrets.token_hex(8) + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return f"/static/uploads/{name}"
