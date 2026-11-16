# Realtime transport & deployment

## Server-Sent Events (default)

Every widget opens one SSE stream for its conversation. The operator panel opens a single *staff* stream for everything.

- Events are delivered by a **process-local** pub/sub (`supchat.sse.sse_manager`). It is fast and needs no infrastructure.
- Each open stream keeps one worker thread busy. Use a threaded server.

### Recommended servers

```bash
# WSGI: one process, many threads
gunicorn myproject.wsgi --workers 1 --threads 32 --timeout 0

# ASGI: supchat switches to an async stream automatically (no thread per client)
uvicorn myproject.asgi:application --workers 1     # or daphne / hypercorn
```

### Several workers or servers

Clients connected to different processes do not see each other's events, unless you add a bridge. `BROADCAST_HOOK` is called on every broadcast. Publish the event there, and in each worker call `sse_manager.deliver(...)` for events that come from other workers.

```python
# myproject/supchat_bridge.py: example with redis-py pub/sub
import json, os, threading, redis
from supchat.sse import sse_manager

r = redis.Redis.from_url(os.environ["REDIS_URL"])
ORIGIN = os.urandom(8).hex()

def publish(conversation_id, event, data, internal):
    r.publish("supchat", json.dumps({"o": ORIGIN, "c": conversation_id, "e": event, "d": data, "i": internal}))

def _listen():
    p = r.pubsub(); p.subscribe("supchat")
    for item in p.listen():
        if item["type"] == "message":
            m = json.loads(item["data"])
            if m["o"] != ORIGIN:                      # local clients already got it
                sse_manager.deliver(m["c"], m["e"], m["d"], m["i"])

threading.Thread(target=_listen, daemon=True).start()

# settings.py
SUPCHAT = {"BROADCAST_HOOK": "myproject.supchat_bridge.publish"}
```

Also switch `CACHES` to a shared backend so rate limits apply across workers.

### Reverse proxies

**Nginx**

```nginx
location /supchat/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header X-Forwarded-For $remote_addr;   # with SUPCHAT["TRUST_PROXY_HEADERS"] = True
    proxy_buffering off;          # required for SSE
    proxy_cache off;
    proxy_read_timeout 1h;
}
```

supchat already sends `X-Accel-Buffering: no` and `Cache-Control: no-cache, no-transform`.

**Apache**

```apache
<Location /supchat/>
    ProxyPass http://127.0.0.1:8000/supchat/ flushpackets=on
    ProxyPassReverse http://127.0.0.1:8000/supchat/
</Location>
```

**Behind a proxy, set `SUPCHAT["TRUST_PROXY_HEADERS"] = True`.** Without it, every visitor appears to come from the proxy's IP. They then share the per-IP limits (`MAX_OPEN_PER_IP`, the rate limit for visitors without a guest id) and the IP hash used for blocking. Make sure the proxy *overwrites* `X-Forwarded-For` (`proxy_set_header X-Forwarded-For $remote_addr;`) so clients can't spoof it.

## WebSocket adapter (optional)

```bash
pip install "django-supchat[channels]"
```

```python
# asgi.py
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from supchat.contrib.channels import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
```

| URL | Who |
|---|---|
| `ws/supchat/<conversation-id>/` | The visitor (cookie, session or `X-Supchat-Guest` header). Sends `{"type": "typing", "is_typing": true}`. |
| `ws/supchat/operator/` | Staff only, every event. |

Frames are `{"event": "...", "data": {...}}`, with the same events and audience rules as SSE. The bundled widget keeps using SSE; the adapter is meant for custom and native clients. It builds on the same process-local manager, so the multi-worker notes above apply.

## Background work

AI replies, webhooks and transcript email run after the database commit, in a daemon thread. Set `SUPCHAT["BACKGROUND"] = "sync"` to run them inline (tests).

## Maintenance

```bash
python manage.py supchat_cleanup            # auto-close idle + purge old (per settings)
python manage.py supchat_cleanup --dry-run
```

Schedule it with cron, systemd timers or Celery beat.
