"""Optional WebSocket transport built on Django Channels.

SSE stays the default (zero dependencies). Install ``django-supchat[channels]`` and
route these consumers in your ASGI app if you prefer WebSockets::

    # asgi.py
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    from django.core.asgi import get_asgi_application
    from supchat.contrib.channels import websocket_urlpatterns

    application = ProtocolTypeRouter({
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    })

Frames are JSON objects ``{"event": "...", "data": {...}}`` with exactly the same
events and audience rules as the SSE streams. Visitors may send
``{"type": "typing", "is_typing": true}``.

Like the SSE manager it builds on, delivery is process-local: run one ASGI worker or
set ``SUPCHAT["BROADCAST_HOOK"]`` for cross-worker fan-out.
"""
from __future__ import annotations

import asyncio
import queue
from http.cookies import SimpleCookie
from types import SimpleNamespace

try:
    from channels.db import database_sync_to_async
    from channels.generic.websocket import AsyncJsonWebsocketConsumer
except ImportError as exc:  # pragma: no cover - exercised only without channels
    raise ImportError("supchat.contrib.channels needs Django Channels: pip install 'django-supchat[channels]'") from exc

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.urls import path

from ..permissions import is_staff_user
from ..services import broadcast_typing, get_conversation_for_request
from ..sse import STAFF_CHANNEL, sse_manager

POLL_SECONDS = 1.0
PING_EVERY = 25


def _request_from_scope(scope) -> SimpleNamespace:
    """A minimal request-like object so the normal permission helpers can be reused."""
    headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
    cookies = SimpleCookie()
    cookies.load(headers.get("cookie", ""))
    meta = {"REMOTE_ADDR": (scope.get("client") or ["unknown"])[0]}
    if "x-supchat-guest" in headers:
        meta["HTTP_X_SUPCHAT_GUEST"] = headers["x-supchat-guest"]
    return SimpleNamespace(
        user=scope.get("user") or AnonymousUser(),
        COOKIES={k: m.value for k, m in cookies.items()},
        META=meta,
    )


class _Base(AsyncJsonWebsocketConsumer):
    staff = False

    async def _start(self, channel: str) -> None:
        self.conn = sse_manager.subscribe(channel, staff=self.staff)
        await self.accept()
        await self.send_json({"event": "connected", "data": {"conversation": channel}})
        self.pump = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        idle = 0.0
        while True:
            try:
                payload = await asyncio.to_thread(self.conn.queue.get, True, POLL_SECONDS)
            except queue.Empty:
                idle += POLL_SECONDS
                if idle >= PING_EVERY:
                    idle = 0.0
                    await self.send_json({"event": "ping", "data": {}})
                continue
            idle = 0.0
            await self.send_json({"event": payload["event"], "data": payload["data"]})

    async def disconnect(self, code):
        task = getattr(self, "pump", None)
        if task:
            task.cancel()
        conn = getattr(self, "conn", None)
        if conn:
            sse_manager.unsubscribe(conn)


class SupchatConsumer(_Base):
    """``ws/supchat/<conversation_id>/`` - visitor stream (internal events excluded)."""

    async def connect(self):
        self.request = _request_from_scope(self.scope)
        cid = str(self.scope["url_route"]["kwargs"]["conversation_id"])
        try:
            self.conversation = await database_sync_to_async(get_conversation_for_request)(self.request, cid)
        except PermissionDenied:
            await self.close(code=4403)
            return
        await self._start(cid)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("type") == "typing":
            try:
                await database_sync_to_async(broadcast_typing)(self.request, self.conversation, bool(content.get("is_typing")))
            except PermissionDenied:
                pass


class SupchatStaffConsumer(_Base):
    """``ws/supchat/operator/`` - every event of every conversation, operators only."""

    staff = True

    async def connect(self):
        user = self.scope.get("user")
        if not await database_sync_to_async(is_staff_user)(user):
            await self.close(code=4403)
            return
        await self._start(STAFF_CHANNEL)


websocket_urlpatterns = [
    path("ws/supchat/operator/", SupchatStaffConsumer.as_asgi()),
    path("ws/supchat/<uuid:conversation_id>/", SupchatConsumer.as_asgi()),
]
