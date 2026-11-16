import json

import pytest

from supchat.sse import SSEManager, event_stream, format_sse, sse_manager, streaming_response


def test_format_sse():
    out = format_sse("message.created", {"a": "é"}, event_id="7")
    assert out == 'id: 7\nevent: message.created\ndata: {"a":"é"}\n\n'


def test_subscribe_broadcast_unsubscribe():
    m = SSEManager()
    c = m.subscribe("c1")
    other = m.subscribe("c2")
    m.broadcast("c1", "e", {"x": 1})
    assert c.queue.get_nowait()["data"] == {"x": 1}
    assert other.queue.empty()
    assert m.active_count() == 2
    m.unsubscribe(c)
    m.unsubscribe(c)  # idempotent
    assert m.active_count() == 1


def test_broadcast_without_subscribers_is_noop():
    SSEManager().broadcast("nobody", "e", {})


def test_cleanup_drops_stale():
    m = SSEManager()
    c = m.subscribe("c1")
    c.last_seen -= 10_000
    m.cleanup(max_age=3600)
    assert m.active_count() == 0


def test_event_stream_flow():
    gen = event_stream("c9")
    assert next(gen).startswith("retry: ")
    assert "event: connected" in next(gen)
    sse_manager.broadcast("c9", "message.created", {"text": "hi"})
    chunk = next(gen)
    assert "event: message.created" in chunk
    assert json.loads(chunk.split("data: ")[1])["text"] == "hi"
    assert sse_manager.active_count() == 1
    gen.close()
    assert sse_manager.active_count() == 0


def test_event_stream_heartbeat(settings):
    settings.SUPCHAT = {"HEARTBEAT_INTERVAL": 0}
    gen = event_stream("c10")
    next(gen)
    next(gen)
    assert next(gen) == ": heartbeat\n\n"
    gen.close()


@pytest.mark.django_db
def test_streaming_response_headers():
    r = streaming_response("c1")
    assert r["Content-Type"] == "text/event-stream"
    assert "no-cache" in r["Cache-Control"]
    assert r["X-Accel-Buffering"] == "no"
    r.close()


@pytest.mark.asyncio
async def test_async_event_stream_yields_live_events(settings):
    from supchat.sse import async_event_stream

    settings.SUPCHAT = {"HEARTBEAT_INTERVAL": 1}
    gen = async_event_stream("c-async", poll=0.05)
    assert (await gen.__anext__()).startswith("retry:")
    assert "connected" in await gen.__anext__()
    sse_manager.broadcast("c-async", "message.created", {"text": "live"})
    assert "live" in await gen.__anext__()
    assert await gen.__anext__() == ": heartbeat\n\n"
    await gen.aclose()
    assert sse_manager.active_count() == 0


@pytest.mark.django_db
def test_streaming_response_picks_async_iterator_for_asgi(rf):
    from django.core.handlers.asgi import ASGIRequest

    asgi_req = ASGIRequest({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}, __import__("io").BytesIO())
    r = streaming_response("c1", request=asgi_req)
    assert r.is_async
    r2 = streaming_response("c1", request=rf.get("/"))
    assert not r2.is_async
    r2.close()
