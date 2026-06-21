# django-supchat

`django-supchat` is a lightweight reusable Django application that adds a secure support chat widget powered by Server-Sent Events (SSE), the Django ORM, and vanilla JavaScript.

It does **not** require Django Channels, WebSockets, Socket.IO, Redis, React, Vue, or a frontend build step.

## Installation

```bash
pip install django-supchat
```

Add the app and URLs:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "supchat",
]

# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path("supchat/", include("supchat.urls")),
]
```

Run migrations:

```bash
python manage.py migrate
```

Render the widget in a template:

```django
{% load supchat %}
{% supchat %}
```

The widget ships with plain CSS/JS and can be overridden with Django's normal template/staticfiles mechanisms.

## Settings

```python
SUPCHAT = {
    "TITLE": "Support",
    "POSITION": "right",        # "right" or "left"
    "THEME": "auto",            # "auto", "light", or "dark"
    "ALLOW_GUEST": True,
    "MAX_MESSAGE_LENGTH": 2000,
}
```

Additional operational settings:

```python
SUPCHAT = {
    "HEARTBEAT_INTERVAL": 25,
    "SSE_RETRY_MS": 5000,
    "GUEST_COOKIE_NAME": "supchat_guest",
    "GUEST_COOKIE_AGE": 60 * 60 * 24 * 365,
    "RATE_LIMIT": {"MESSAGES": 30, "WINDOW": 60},
    "RATE_LIMIT_CALLBACK": None,  # callable(request, action) -> bool
}
```

## Security model

- POST endpoints use Django CSRF protection.
- Guest identity is stored in a signed, HTTP-only cookie; client-supplied guest IDs are ignored.
- Conversation access is checked for every endpoint, including SSE.
- Message text is stripped of HTML, control characters are removed, and length is capped.
- The frontend inserts messages with `textContent`, never `innerHTML`.
- Rate limiting is provided through a cache-backed default and a pluggable hook.

## Operators

Create `Operator` records in the Django admin for staff/support users. Operators can view conversations and may be assigned through the service layer:

```python
from supchat.services import assign_operator

assign_operator(request, conversation)
```

## SSE deployment notes

The built-in SSE manager is intentionally dependency-free and process-local. It works well for simple deployments and development. If your production deployment uses multiple worker processes, clients connected to a different worker may not receive in-memory broadcasts. You can still use the package without Redis; for cross-worker fanout, call `supchat.sse.sse_manager.broadcast()` from your own cache/queue integration.

Recommended proxy settings for SSE:

- Disable response buffering for `/supchat/*/events/`.
- Use reasonable worker timeouts for long-lived HTTP responses.

## Customization

Override any of these in your project:

- `templates/supchat/widget.html`
- `static/supchat/supchat.css`
- `static/supchat/supchat.js`

The template tag accepts small per-render overrides:

```django
{% supchat title="Help" position="left" theme="dark" %}
```

## Public API

The service layer is the stable integration point:

- `get_or_create_conversation(request)`
- `send_message(request, conversation, text)`
- `close_conversation(request, conversation)`
- `assign_operator(request, conversation, operator=None)`
- `mark_messages_read(request, conversation, message_ids=None)`

## Testing

For package development:

```bash
pip install -e '.[test]'
pytest
```
