"""A minimal in-memory WebSocket hub so waiter/admin screens update live.

When an order is paid or served, we broadcast a small JSON event. Every connected
staff browser receives it and updates instantly — no page refresh, no polling.

For a single-server pilot this is perfect. If you ever scale to multiple servers,
swap this for Redis pub/sub (the broadcast() call sites stay the same).
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        # Copy the list so a disconnect mid-loop can't break iteration.
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


manager = ConnectionManager()
