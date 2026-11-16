from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.http import StreamingHttpResponse
from django.utils.module_loading import import_string

from .conf import supchat_settings

STAFF_CHANNEL = "__staff__"


@dataclass
class _Connection:
    id: str
    conversation_id: str
    staff: bool = False
    queue: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class SSEManager:
    """Process-local SSE pub/sub manager with audience scoping.

    * Visitor connections subscribe to one conversation and never receive
      events flagged ``internal`` (operator notes, tag changes, ...).
    * Staff connections subscribe to ``STAFF_CHANNEL`` and receive *every* event of
      *every* conversation, so the operator panel needs a single stream.

    Cross-worker fan-out: set ``SUPCHAT["BROADCAST_HOOK"]`` to a dotted path of a
    callable ``(conversation_id, event, data, internal)``; it is invoked on every
    broadcast so you can publish to Redis / a queue and call ``deliver`` from
    subscribers in other workers.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, dict[str, _Connection]] = {}

    def subscribe(self, conversation_id: str, staff: bool = False) -> _Connection:
        conn = _Connection(id=uuid.uuid4().hex, conversation_id=str(conversation_id), staff=staff)
        with self._lock:
            self._connections.setdefault(conn.conversation_id, {})[conn.id] = conn
        return conn

    def unsubscribe(self, conn: _Connection) -> None:
        with self._lock:
            bucket = self._connections.get(conn.conversation_id)
            if not bucket:
                return
            bucket.pop(conn.id, None)
            if not bucket:
                self._connections.pop(conn.conversation_id, None)

    def deliver(self, conversation_id: str, event: str, data: dict[str, Any], internal: bool = False) -> None:
        """Deliver to local connections only (used by cross-worker bridges)."""
        payload = {"event": event, "data": data, "ts": time.time()}
        with self._lock:
            targets = list(self._connections.get(str(conversation_id), {}).values())
            targets += list(self._connections.get(STAFF_CHANNEL, {}).values())
        for conn in targets:
            if internal and not conn.staff:
                continue
            conn.queue.put_nowait(payload)

    def broadcast(self, conversation_id: str, event: str, data: dict[str, Any], internal: bool = False) -> None:
        self.deliver(conversation_id, event, data, internal)
        hook = supchat_settings.get("BROADCAST_HOOK")
        if hook:
            try:
                (import_string(hook) if isinstance(hook, str) else hook)(str(conversation_id), event, data, internal)
            except Exception:  # a broken bridge must never break chatting
                pass

    def cleanup(self, max_age: int = 3600) -> None:
        cutoff = time.time() - max_age
        with self._lock:
            for conversation_id, bucket in list(self._connections.items()):
                for conn_id, conn in list(bucket.items()):
                    if conn.last_seen < cutoff:
                        bucket.pop(conn_id, None)
                if not bucket:
                    self._connections.pop(conversation_id, None)

    def active_count(self) -> int:
        with self._lock:
            return sum(len(bucket) for bucket in self._connections.values())


sse_manager = SSEManager()


def format_sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    for line in encoded.splitlines() or [""]:
        lines.append(f"data: {line}")
    lines.append("")
    return "\n".join(lines) + "\n"


def event_stream(conversation_id: str, staff: bool = False) -> Iterable[str]:
    conn = sse_manager.subscribe(str(conversation_id), staff=staff)
    heartbeat = int(supchat_settings.get("HEARTBEAT_INTERVAL"))
    retry_ms = int(supchat_settings.get("SSE_RETRY_MS"))
    try:
        yield f"retry: {retry_ms}\n\n"
        yield format_sse("connected", {"conversation": str(conversation_id)})
        while True:
            try:
                payload = conn.queue.get(timeout=heartbeat)
            except queue.Empty:
                conn.last_seen = time.time()
                yield ": heartbeat\n\n"
                continue
            conn.last_seen = time.time()
            yield format_sse(payload["event"], payload["data"])
    except GeneratorExit:
        raise
    finally:
        sse_manager.unsubscribe(conn)


async def async_event_stream(conversation_id: str, staff: bool = False, poll: float = 1.0):
    """ASGI variant: Django would buffer a *sync* endless iterator, so stream asynchronously."""
    conn = sse_manager.subscribe(str(conversation_id), staff=staff)
    heartbeat = int(supchat_settings.get("HEARTBEAT_INTERVAL"))
    retry_ms = int(supchat_settings.get("SSE_RETRY_MS"))
    idle = 0.0
    try:
        yield f"retry: {retry_ms}\n\n"
        yield format_sse("connected", {"conversation": str(conversation_id)})
        while True:
            try:
                payload = await asyncio.to_thread(conn.queue.get, True, poll)
            except queue.Empty:
                idle += poll
                if idle >= heartbeat:
                    idle = 0.0
                    conn.last_seen = time.time()
                    yield ": heartbeat\n\n"
                continue
            idle = 0.0
            conn.last_seen = time.time()
            yield format_sse(payload["event"], payload["data"])
    finally:
        sse_manager.unsubscribe(conn)


def _is_asgi(request) -> bool:
    try:
        from django.core.handlers.asgi import ASGIRequest
    except ImportError:  # pragma: no cover
        return False
    return isinstance(request, ASGIRequest)


def streaming_response(conversation_id: str, staff: bool = False, request=None) -> StreamingHttpResponse:
    stream = async_event_stream if (request is not None and _is_asgi(request)) else event_stream
    response = StreamingHttpResponse(stream(str(conversation_id), staff=staff), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response
