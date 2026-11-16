# Webhooks

Notify Slack, Discord or your own service when something happens. Add endpoints in **Django admin → Supchat → Webhook endpoints**.

| Field | Meaning |
|---|---|
| Name | Label shown in the operator Settings page |
| URL | The incoming-webhook URL |
| Kind | `generic`, `slack` or `discord` |
| Secret | HMAC key (generic only) |
| Events | `*` or a comma-separated list |
| Active | On/off |

The last HTTP status and error of each endpoint are recorded and shown in the panel. Superusers can send a test event from **Settings → Webhooks → Test**.

## Events

| Event | When |
|---|---|
| `conversation.started` | The first message of a new conversation is sent |
| `message.created` | A non-internal message is sent (visitor, operator or bot) |
| `conversation.closed` | A conversation is closed |
| `conversation.rated` | A visitor submits a rating |

Webhooks are sent after the database commit, in the background, with a timeout (`WEBHOOK_TIMEOUT`). A failing endpoint never affects chatting.

## Payloads

**Slack** → `{"text": "Ali: hello"}`. **Discord** → `{"content": "Ali: hello"}`.

**Generic**:

```http
POST /your/hook
Content-Type: application/json
X-Supchat-Event: message.created
X-Supchat-Signature: sha256=5d41402abc4b2a76b9719d911017c592...

{"event": "message.created",
 "data": {"conversation": "1b8e…", "participant": "Ali", "status": "open",
          "message_id": 42, "sender_type": "guest", "text": "hello"},
 "ts": 1763290000}
```

### Verifying the signature

```python
import hashlib, hmac

def verify(request, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, request.headers.get("X-Supchat-Signature", ""))
```

## SSRF protection

Only `http(s)` URLs are allowed. By default, targets that resolve to private, loopback or link-local addresses are refused (this blocks cloud metadata endpoints). Redirects are not followed. For local development set `WEBHOOK_ALLOW_PRIVATE = True`.
