"""FastAPI application: routes for the customer, waiter and admin flows.

Read this file top-to-bottom to understand the whole system — it wires together
the database, payments, JWT tokens and the realtime WebSocket hub.
"""
from __future__ import annotations

import base64
import io
import json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
import qrcode
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from . import images, payments, security
from .config import settings
from .database import get_session, init_db
from .models import MenuItem, Order, OrderStatus, User
from .realtime import manager
from .seed import seed_menu


def naive_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; strip tzinfo so comparisons never mix types."""
    return dt.replace(tzinfo=None) if dt and dt.tzinfo else dt


def qr_data_uri(text: str) -> str:
    """Render a QR code for `text` server-side and return it as a PNG data URI.

    Doing this on the server avoids depending on a client-side QR library/CDN and
    works offline (the image is embedded in the page)."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=6, border=2
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_menu()
    yield


app = FastAPI(title="Tea Shop Token System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Make ₹ formatting available inside templates.
templates.env.filters["rupees"] = lambda paise: f"₹{paise / 100:.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def order_to_public_dict(o: Order) -> dict:
    return {
        "public_id": o.public_id,
        "items": json.loads(o.items_json),
        "total_paise": o.total_paise,
        "table_number": o.table_number,
        "status": o.status.value,
        "created_at": o.created_at.isoformat(),
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "served_at": o.served_at.isoformat() if o.served_at else None,
    }


def menu_item_dict(i: MenuItem) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "description": i.description,
        "price_paise": i.price_paise,
        "price_rupees": round(i.price_paise / 100, 2),
        "category": i.category,
        "emoji": i.emoji,
        "image_url": i.image_url,
        "available": i.available,
    }


def current_session(request: Request) -> dict | None:
    return security.decode_session(request.cookies.get("staff_session"))


def require_staff(request: Request) -> dict:
    """Any logged-in staff member (admin or waiter)."""
    s = current_session(request)
    if not s or s.get("role") not in ("admin", "waiter"):
        raise HTTPException(status_code=401, detail="Not logged in")
    return s


def require_admin(request: Request) -> dict:
    """Admin (owner) only — menu, analytics, orders, staff management."""
    s = current_session(request)
    if not s or s.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return s


# --------------------------------------------------------------------------- #
# Public pages (HTML)
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def page_menu(request: Request, session: Session = Depends(get_session)):
    items = session.exec(select(MenuItem).where(MenuItem.available)).all()
    categories: dict[str, list[MenuItem]] = {}
    for it in items:
        categories.setdefault(it.category, []).append(it)
    return templates.TemplateResponse(
        "menu.html",
        {
            "request": request,
            "categories": categories,
            "shop_name": settings.SHOP_NAME,
            "payment_mode": settings.PAYMENT_MODE,
        },
    )


@app.get("/my-tokens", response_class=HTMLResponse)
def page_my_tokens(request: Request):
    # The list itself lives in the browser's localStorage (customers aren't logged
    # in); this page just renders it and refreshes each token's status.
    return templates.TemplateResponse(
        "my_tokens.html", {"request": request, "shop_name": settings.SHOP_NAME}
    )


@app.get("/t/{public_id}", response_class=HTMLResponse)
def page_token(request: Request, public_id: str, session: Session = Depends(get_session)):
    order = session.exec(select(Order).where(Order.public_id == public_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Re-issue the (deterministic) JWT so the QR can be verified offline. A served
    # order has no jti, so there is no valid token to embed — the QR falls back to
    # just the order id and verification will correctly report "already served".
    token = ""
    if order.status == OrderStatus.PAID and order.token_jti:
        token = security.issue_token(
            public_id=order.public_id,
            jti=order.token_jti,
            items=json.loads(order.items_json),
            total_paise=order.total_paise,
        )
    return templates.TemplateResponse(
        "token.html",
        {
            "request": request,
            "order": order_to_public_dict(order),
            "token": token,
            "qr_data_uri": qr_data_uri(order.public_id),
            "shop_name": settings.SHOP_NAME,
        },
    )


@app.get("/waiter", response_class=HTMLResponse)
def page_waiter(request: Request):
    s = current_session(request)
    if not s or s.get("role") not in ("admin", "waiter"):
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        "waiter.html",
        {
            "request": request,
            "shop_name": settings.SHOP_NAME,
            "is_admin": s.get("role") == "admin",
            "username": s.get("username", ""),
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def page_admin(request: Request):
    s = current_session(request)
    if not s or s.get("role") != "admin":
        return RedirectResponse("/admin/login")
    return templates.TemplateResponse(
        "admin.html", {"request": request, "shop_name": settings.SHOP_NAME}
    )


def _set_session(resp, role: str, username: str = ""):
    resp.set_cookie(
        "staff_session",
        security.issue_session_cookie(role, username),
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
    )


# ---- Waiter login (username + password account created by the admin) -------- #
@app.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "shop_name": settings.SHOP_NAME}
    )


@app.post("/login")
def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    user = session.exec(
        select(User).where(User.username == username.strip())
    ).first()
    if not user or not user.active or not security.verify_password(password, user.password_hash):
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/waiter", status_code=303)
    _set_session(resp, user.role, user.username)
    return resp


# ---- Admin login (the owner, via ADMIN_PASSWORD) --------------------------- #
@app.get("/admin/login", response_class=HTMLResponse)
def page_admin_login(request: Request):
    return templates.TemplateResponse(
        "admin_login.html", {"request": request, "shop_name": settings.SHOP_NAME}
    )


@app.post("/admin/login")
def do_admin_login(password: str = Form(...)):
    if password != settings.ADMIN_PASSWORD:
        return RedirectResponse("/admin/login?error=1", status_code=303)
    resp = RedirectResponse("/admin", status_code=303)
    _set_session(resp, "admin", "admin")
    return resp


@app.get("/logout")
def logout(request: Request):
    # Send each role back to its own login screen.
    s = current_session(request)
    dest = "/admin/login" if s and s.get("role") == "admin" else "/login"
    resp = RedirectResponse(dest, status_code=303)
    resp.delete_cookie("staff_session")
    return resp


# --------------------------------------------------------------------------- #
# Customer API: menu -> create order -> pay -> get token
# --------------------------------------------------------------------------- #
@app.get("/api/menu")
def api_menu(session: Session = Depends(get_session)):
    items = session.exec(select(MenuItem).where(MenuItem.available)).all()
    return [menu_item_dict(i) for i in items]


@app.post("/api/orders")
async def api_create_order(payload: dict, session: Session = Depends(get_session)):
    """Body: {"items": [{"id": 1, "qty": 2}, ...]}.

    We re-price every item from the database — never trust prices sent by the
    client, or a customer could pay ₹0 for everything.
    """
    raw_items = payload.get("items") or []
    if not raw_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    table_number = (payload.get("table_number") or "").strip() or None

    line_items: list[dict] = []
    total = 0
    for entry in raw_items:
        item = session.get(MenuItem, int(entry["id"]))
        qty = int(entry.get("qty", 1))
        if not item or not item.available or qty < 1:
            continue
        line_total = item.price_paise * qty
        total += line_total
        line_items.append(
            {"id": item.id, "name": item.name, "emoji": item.emoji,
             "image_url": item.image_url, "qty": qty, "price_paise": item.price_paise}
        )

    if not line_items:
        raise HTTPException(status_code=400, detail="No valid items in cart")

    public_id = security.new_public_id()
    provider = payments.create_provider_order(total, receipt=public_id)

    order = Order(
        public_id=public_id,
        items_json=json.dumps(line_items),
        total_paise=total,
        table_number=table_number,
        status=OrderStatus.PENDING_PAYMENT,
        provider_order_id=provider["provider_order_id"],
        payment_provider=provider["mode"],
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    return {
        "public_id": order.public_id,
        "total_paise": total,
        "payment": provider,
        "shop_name": settings.SHOP_NAME,
    }


@app.post("/api/orders/{public_id}/pay")
async def api_confirm_payment(
    public_id: str, payload: dict, session: Session = Depends(get_session)
):
    """Verify payment, flip the order to PAID and mint the signed token.

    Body (razorpay): {razorpay_payment_id, razorpay_signature}
    Body (demo): {} — auto verified.
    """
    order = session.exec(select(Order).where(Order.public_id == public_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != OrderStatus.PENDING_PAYMENT:
        # Idempotent: if already paid just return the existing token.
        if order.status == OrderStatus.PAID and order.token_jti:
            return _token_response(order)
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    payment_id = payload.get("razorpay_payment_id", "demo_payment")
    signature = payload.get("razorpay_signature", "")

    ok = payments.verify_payment(
        provider_order_id=order.provider_order_id,
        payment_id=payment_id,
        signature=signature,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    order.status = OrderStatus.PAID
    order.paid_at = datetime.now(timezone.utc)
    order.payment_ref = payment_id
    order.token_jti = security.new_jti()
    session.add(order)
    session.commit()
    session.refresh(order)

    # Tell every waiter screen a new order just came in.
    await manager.broadcast({"type": "order_paid", "order": order_to_public_dict(order)})
    return _token_response(order)


def _token_response(order: Order) -> dict:
    items = json.loads(order.items_json)
    token = security.issue_token(
        public_id=order.public_id,
        jti=order.token_jti,
        items=items,
        total_paise=order.total_paise,
    )
    return {
        "public_id": order.public_id,
        "token": token,
        "items": items,
        "total_paise": order.total_paise,
        "status": order.status.value,
    }


@app.get("/api/orders/{public_id}")
def api_order_status(public_id: str, session: Session = Depends(get_session)):
    """Polled by the customer's token page as a fallback when WebSocket is down."""
    order = session.exec(select(Order).where(Order.public_id == public_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_to_public_dict(order)


# --------------------------------------------------------------------------- #
# Token verification (waiter scans QR / pastes token)
# --------------------------------------------------------------------------- #
def _validate_for_serving(order: Order | None, *, jti: str | None = None) -> dict:
    """Shared rules for whether an order can be served right now."""
    if not order:
        return {"valid": False, "reason": "No order found for that code"}
    # Serving clears the jti, so check served status first for a clearer message.
    if order.status == OrderStatus.SERVED:
        return {"valid": False, "reason": "Already served", "order": order_to_public_dict(order)}
    # jti is only checked for QR/JWT verification (cryptographic path).
    if jti is not None and order.token_jti != jti:
        return {"valid": False, "reason": "Token revoked"}
    if order.status != OrderStatus.PAID:
        return {"valid": False, "reason": f"Order is {order.status.value}"}
    return {"valid": True, "order": order_to_public_dict(order)}


@app.post("/api/verify")
def api_verify(payload: dict, session: Session = Depends(get_session)):
    """Verify a token three ways:
    - {"token": "<jwt>"}      QR scan / paste — cryptographically checks the signature.
    - {"public_id": "T-XXXX"} the short code on the token — looked up in the DB.
    """
    token = (payload.get("token") or "").strip()
    public_id = (payload.get("public_id") or "").strip().upper()

    if token:
        try:
            claims = security.decode_token(token)
        except jwt.ExpiredSignatureError:
            return {"valid": False, "reason": "Token expired"}
        except jwt.PyJWTError:
            return {"valid": False, "reason": "Invalid signature — possible fake"}
        order = session.exec(select(Order).where(Order.public_id == claims["sub"])).first()
        return _validate_for_serving(order, jti=claims.get("jti"))

    if public_id:
        if not public_id.startswith("T-"):
            public_id = "T-" + public_id          # allow typing just the code part
        order = session.exec(select(Order).where(Order.public_id == public_id)).first()
        return _validate_for_serving(order)

    return {"valid": False, "reason": "Enter a code or scan a token"}


# --------------------------------------------------------------------------- #
# Staff API: list active orders, mark served, stats
# --------------------------------------------------------------------------- #
@app.get("/api/staff/active")
def api_active_orders(request: Request, session: Session = Depends(get_session)):
    require_staff(request)
    orders = session.exec(
        select(Order).where(Order.status == OrderStatus.PAID).order_by(Order.paid_at)
    ).all()
    return [order_to_public_dict(o) for o in orders]


@app.post("/api/staff/orders/{public_id}/serve")
async def api_serve(
    public_id: str, request: Request, session: Session = Depends(get_session)
):
    require_staff(request)
    order = session.exec(select(Order).where(Order.public_id == public_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == OrderStatus.SERVED:
        return order_to_public_dict(order)
    if order.status != OrderStatus.PAID:
        raise HTTPException(status_code=409, detail=f"Order is {order.status.value}")

    # Revoking the jti is what actually kills the token: a re-shown screenshot or
    # a duplicate will now fail /api/verify.
    order.status = OrderStatus.SERVED
    order.served_at = datetime.now(timezone.utc)
    order.token_jti = None
    session.add(order)
    session.commit()
    session.refresh(order)

    await manager.broadcast({"type": "order_served", "order": order_to_public_dict(order)})
    return order_to_public_dict(order)


@app.get("/api/staff/stats")
def api_stats(request: Request, session: Session = Depends(get_session)):
    require_staff(request)
    # SQLite returns naive datetimes (UTC), so compare against a naive UTC midnight.
    start_of_day = datetime.now(timezone.utc).replace(
        tzinfo=None, hour=0, minute=0, second=0, microsecond=0
    )
    served = session.exec(
        select(Order).where(Order.status == OrderStatus.SERVED)
    ).all()
    paid = session.exec(select(Order).where(Order.status == OrderStatus.PAID)).all()

    today = [o for o in served if o.served_at and naive_utc(o.served_at) >= start_of_day]
    revenue_today = sum(o.total_paise for o in today)
    revenue_all = sum(o.total_paise for o in served)

    return {
        "active_tokens": len(paid),
        "served_today": len(today),
        "revenue_today_paise": revenue_today,
        "served_total": len(served),
        "revenue_total_paise": revenue_all,
        "recent": [order_to_public_dict(o) for o in sorted(
            served, key=lambda o: o.served_at or o.created_at, reverse=True
        )[:10]],
    }


# --------------------------------------------------------------------------- #
# Admin API: menu management (create / edit / delete / availability)
# --------------------------------------------------------------------------- #
@app.get("/api/admin/menu")
def admin_list_menu(request: Request, session: Session = Depends(get_session)):
    """All items, including unavailable ones (unlike the public /api/menu)."""
    require_admin(request)
    items = session.exec(select(MenuItem).order_by(MenuItem.category, MenuItem.id)).all()
    return [menu_item_dict(i) for i in items]


@app.post("/api/admin/menu")
async def admin_create_menu(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),            # rupees, e.g. 15 or 15.50
    description: str = Form(""),
    category: str = Form("Tea"),
    emoji: str = Form("🍵"),
    available: bool = Form(True),
    image: UploadFile | None = File(None),
    session: Session = Depends(get_session),
):
    require_admin(request)
    image_url = ""
    if image is not None and image.filename:
        image_url = images.upload_image(await image.read(), image.filename) or ""

    item = MenuItem(
        name=name.strip(),
        description=description.strip(),
        price_paise=max(0, round(price * 100)),
        category=category.strip() or "Tea",
        emoji=emoji.strip() or "🍵",
        image_url=image_url,
        available=available,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return menu_item_dict(item)


@app.put("/api/admin/menu/{item_id}")
async def admin_update_menu(
    item_id: int,
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    description: str = Form(""),
    category: str = Form("Tea"),
    emoji: str = Form("🍵"),
    available: bool = Form(True),
    image: UploadFile | None = File(None),
    session: Session = Depends(get_session),
):
    require_admin(request)
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.name = name.strip()
    item.description = description.strip()
    item.price_paise = max(0, round(price * 100))
    item.category = category.strip() or "Tea"
    item.emoji = emoji.strip() or "🍵"
    item.available = available
    if image is not None and image.filename:
        item.image_url = images.upload_image(await image.read(), image.filename) or item.image_url

    session.add(item)
    session.commit()
    session.refresh(item)
    return menu_item_dict(item)


@app.post("/api/admin/menu/{item_id}/availability")
def admin_toggle_availability(
    item_id: int, request: Request, session: Session = Depends(get_session)
):
    require_admin(request)
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.available = not item.available
    session.add(item)
    session.commit()
    session.refresh(item)
    return menu_item_dict(item)


@app.delete("/api/admin/menu/{item_id}")
def admin_delete_menu(
    item_id: int, request: Request, session: Session = Depends(get_session)
):
    require_admin(request)
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    session.delete(item)
    session.commit()
    return {"deleted": item_id}


# --------------------------------------------------------------------------- #
# Admin API: full order view with filters + analytics
# --------------------------------------------------------------------------- #
@app.get("/api/admin/orders")
def admin_orders(
    request: Request,
    status: str = "all",                 # all | pending | completed
    session: Session = Depends(get_session),
):
    """Complete order view. 'pending' = paid but not yet delivered, 'completed'
    = served/delivered. Each order carries a `delivered` flag and table number."""
    require_admin(request)
    query = select(Order)
    if status == "pending":
        query = query.where(Order.status == OrderStatus.PAID)
    elif status == "completed":
        query = query.where(Order.status == OrderStatus.SERVED)
    else:
        query = query.where(Order.status.in_([OrderStatus.PAID, OrderStatus.SERVED]))

    orders = session.exec(query).all()
    orders.sort(key=lambda o: o.paid_at or o.created_at, reverse=True)

    result = []
    for o in orders:
        d = order_to_public_dict(o)
        d["delivered"] = o.status == OrderStatus.SERVED
        result.append(d)
    return result


@app.delete("/api/admin/orders/{public_id}")
def admin_delete_order(
    public_id: str, request: Request, session: Session = Depends(get_session)
):
    """Delete a finished order from history. An active (paid, not-yet-served)
    order can't be deleted — serve it first so its live token isn't orphaned."""
    require_admin(request)
    order = session.exec(select(Order).where(Order.public_id == public_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == OrderStatus.PAID:
        raise HTTPException(status_code=409, detail="Order is still active — serve it first")
    session.delete(order)
    session.commit()
    return {"deleted": public_id}


@app.get("/api/admin/analytics")
def admin_analytics(request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = start_of_day - timedelta(days=6)  # last 7 calendar days incl. today

    served = session.exec(
        select(Order).where(Order.status == OrderStatus.SERVED)
    ).all()
    pending = session.exec(select(Order).where(Order.status == OrderStatus.PAID)).all()

    def served_when(o: Order) -> datetime:
        return naive_utc(o.served_at) or naive_utc(o.created_at)

    today = [o for o in served if served_when(o) >= start_of_day]

    # 7-day revenue series for the chart.
    days: list[dict] = []
    for i in range(7):
        day = (week_ago + timedelta(days=i)).date()
        day_orders = [o for o in served if served_when(o).date() == day]
        days.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%a"),
                "revenue_paise": sum(o.total_paise for o in day_orders),
                "orders": len(day_orders),
            }
        )

    # Top-selling items (by quantity) across all served orders.
    counter: Counter = Counter()
    revenue_by_item: Counter = Counter()
    for o in served:
        for line in json.loads(o.items_json):
            counter[line["name"]] += line["qty"]
            revenue_by_item[line["name"]] += line["qty"] * line["price_paise"]
    top_items = [
        {"name": name, "qty": qty, "revenue_paise": revenue_by_item[name]}
        for name, qty in counter.most_common(5)
    ]

    return {
        "revenue_today_paise": sum(o.total_paise for o in today),
        "revenue_week_paise": sum(o.total_paise for o in served if served_when(o) >= week_ago),
        "revenue_total_paise": sum(o.total_paise for o in served),
        "orders_today": len(today),
        "served_total": len(served),
        "pending_count": len(pending),
        "avg_order_paise": round(sum(o.total_paise for o in served) / len(served)) if served else 0,
        "days": days,
        "top_items": top_items,
    }


# --------------------------------------------------------------------------- #
# Admin API: waiter account management (admin creates waiters + sets passwords)
# --------------------------------------------------------------------------- #
def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "active": u.active,
        "created_at": u.created_at.isoformat(),
    }


@app.get("/api/admin/users")
def admin_list_users(request: Request, session: Session = Depends(get_session)):
    require_admin(request)
    users = session.exec(select(User).order_by(User.username)).all()
    return [user_dict(u) for u in users]


@app.post("/api/admin/users")
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    require_admin(request)
    username = username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=username,
        password_hash=security.hash_password(password),
        role="waiter",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user_dict(user)


@app.post("/api/admin/users/{user_id}/password")
def admin_reset_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    require_admin(request)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    user.password_hash = security.hash_password(password)
    session.add(user)
    session.commit()
    return user_dict(user)


@app.post("/api/admin/users/{user_id}/active")
def admin_toggle_user(
    user_id: int, request: Request, session: Session = Depends(get_session)
):
    require_admin(request)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.active = not user.active
    session.add(user)
    session.commit()
    return user_dict(user)


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id: int, request: Request, session: Session = Depends(get_session)
):
    require_admin(request)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()
    return {"deleted": user_id}


# --------------------------------------------------------------------------- #
# WebSocket for live staff updates
# --------------------------------------------------------------------------- #
@app.websocket("/ws/staff")
async def ws_staff(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect messages from the client; this keeps the socket open.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


# --------------------------------------------------------------------------- #
# PWA support files served from root scope
# --------------------------------------------------------------------------- #
@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {
            "name": f"{settings.SHOP_NAME} Tokens",
            "short_name": "Tea Token",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0b1120",
            "theme_color": "#0b1120",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        }
    )


@app.get("/sw.js")
def service_worker():
    # Served from root so its scope covers the whole site.
    with open("static/sw.js", "r", encoding="utf-8") as f:
        return Response(content=f.read(), media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "payment_mode": settings.PAYMENT_MODE}
