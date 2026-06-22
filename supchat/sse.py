from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.http import StreamingHttpResponse

from .conf import supchat_settings


@dataclass
class _Connection:
    id: str
    conversation_id: str
    queue: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class SSEManager:
    """Process-local SSE pub/sub manager.

    It intentionally has no external dependency. In multi-process deployments events are
    delivered to clients connected to the same worker; projects needing cross-worker
    fanout can call `broadcast` from their own cache/queue integration hooks later.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, dict[str, _Connection]] = {}

    def subscribe(self, conversation_id: str) -> _Connection:
        conn = _Connection(id=uuid.uuid4().hex, conversation_id=str(conversation_id))
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

    def broadcast(self, conversation_id: str, event: str, data: dict[str, Any]) -> None:
        payload = {"event": event, "data": data, "ts": time.time()}
        with self._lock:
            connections = list(self._connections.get(str(conversation_id), {}).values())
        for conn in connections:
            try:
                conn.queue.put_nowait(payload)
            except queue.Full:  # default queues are unbounded; defensive only
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


def event_stream(conversation_id: str) -> Iterable[str]:
    conn = sse_manager.subscribe(str(conversation_id))
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


def streaming_response(conversation_id: str) -> StreamingHttpResponse:
    response = StreamingHttpResponse(event_stream(str(conversation_id)), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response
