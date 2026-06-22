<div align="center">

# 💬 django-supchat

### A Lightweight, Real-Time Support Chat for Django

[![PyPI version](https://img.shields.io/pypi/v/django-supchat.svg?logo=pypi&logoColor=white&labelColor=3776AB&color=informational)](https://pypi.org/project/django-supchat/)
[![Python Versions](https://img.shields.io/pypi/pyversions/django-supchat.svg?logo=python&logoColor=white&labelColor=3776AB)](https://pypi.org/project/django-supchat/)
[![Django Versions](https://img.shields.io/pypi/frameworkversions/django/django-supchat.svg?logo=django&logoColor=white&labelColor=092E20)](https://pypi.org/project/django-supchat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://static.pepy.tech/badge/django-supchat)](https://pepy.tech/project/django-supchat)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Zero dependencies. No WebSockets. No Redis. No React.**<br>
Just Django, vanilla JS, and Server-Sent Events.

[Installation](#-quick-start) • [Demo](#-screenshots) • [Documentation](#-documentation) • [Examples](#-examples)

</div>

---

## ✨ Overview

**django-supchat** is a production-ready, drop-in support chat widget for Django projects. It provides a beautiful, real-time chat experience between website visitors (guests or authenticated users) and your support team — all powered by Django's ORM and Server-Sent Events (SSE).

> 🎯 **Philosophy:** Ship a powerful chat system without the complexity of WebSockets, Redis, or a frontend build step. Just `pip install` and go.

---

## 🚀 Key Features

<table>
<tr>
<td width="50%">

### 🎨 Frontend
- ✨ Modern glassmorphism UI with smooth animations
- 🌓 Auto Light/Dark theme (respects OS preference)
- 🌐 Auto bilingual (Persian/English) with RTL support
- ⌨️ Real-time typing indicators
- ✅ Read receipts with visual feedback
- 📱 Fully responsive (mobile fullscreen)
- ♿ WCAG 2.1 accessible
- 🎭 Customizable colors via CSS variables

</td>
<td width="50%">

### ⚡ Backend
- 🔌 **Zero external dependencies** — no Redis, no Channels
- 📡 Real-time via Server-Sent Events (SSE)
- 🔒 Signed, HTTP-only guest cookies
- 🛡️ CSRF protection on all POST endpoints
- 🚦 Built-in rate limiting (pluggable)
- 🧹 HTML sanitization & control char stripping
- 👥 Multi-operator support with assignment
- 📊 Analytics dashboard with charts

</td>
</tr>
</table>

---

## 📦 Quick Start

Get up and running in under 2 minutes.

### 1. Install

```bash
pip install django-supchat
```

### 2. Configure Django

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "supchat",
]

# Optional: Customize the widget
SUPCHAT = {
    "TITLE": "Support",
    "POSITION": "right",        # "right" or "left"
    "THEME": "auto",            # "auto", "light", or "dark"
    "ALLOW_GUEST": True,
    "MAX_MESSAGE_LENGTH": 2000,
}
```

### 3. Add URLs

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    # ...
    path("supchat/", include("supchat.urls")),
]
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Render the Widget

```django
{% load supchat %}

<!DOCTYPE html>
<html lang="en">
<head>
    <title>My Site</title>
</head>
<body>
    <h1>Welcome to my site!</h1>
    
    {% supchat %}
</body>
</html>
```

That's it! 🎉 Your chat widget is live.

---

## 📚 Documentation

### Configuration Reference

#### Widget Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `TITLE` | `str` | `"Support"` | Widget title displayed in header |
| `POSITION` | `str` | `"right"` | Widget position: `"right"` or `"left"` |
| `THEME` | `str` | `"auto"` | Theme: `"auto"`, `"light"`, or `"dark"` |
| `ALLOW_GUEST` | `bool` | `True` | Allow anonymous visitors to chat |
| `MAX_MESSAGE_LENGTH` | `int` | `2000` | Maximum characters per message |

#### Advanced Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `HEARTBEAT_INTERVAL` | `int` | `25` | SSE heartbeat interval (seconds) |
| `SSE_RETRY_MS` | `int` | `5000` | SSE reconnection delay (ms) |
| `GUEST_COOKIE_NAME` | `str` | `"supchat_guest"` | Name of the guest identity cookie |
| `GUEST_COOKIE_AGE` | `int` | `31536000` | Cookie lifetime (1 year in seconds) |
| `RATE_LIMIT` | `dict` | `{"MESSAGES": 30, "WINDOW": 60}` | Default rate limit config |
| `RATE_LIMIT_CALLBACK` | `callable` | `None` | Custom rate limit function |

#### Per-Render Overrides

You can override settings per template render:

```django
{% supchat title="Help Desk" position="left" theme="dark" %}
```

---

## 🔐 Security Model

django-supchat takes security seriously:

- ✅ **CSRF Protection** — All POST endpoints require valid CSRF tokens
- ✅ **Signed Guest Cookies** — Guest identity stored in signed, HTTP-only cookies
- ✅ **Conversation Access Control** — Every endpoint (including SSE) verifies access
- ✅ **Input Sanitization** — HTML stripped, control chars removed, length capped
- ✅ **XSS Prevention** — Frontend uses `textContent`, never `innerHTML`
- ✅ **Rate Limiting** — Cache-backed default + pluggable hook for custom logic

### Custom Rate Limiting

```python
# settings.py
def my_rate_limiter(request, action):
    # Return True to allow, False to deny
    if request.user.is_staff:
        return True
    return False  # Custom logic

SUPCHAT = {
    "RATE_LIMIT_CALLBACK": my_rate_limiter,
}
```

---

## 👥 Operator Management

### Creating Operators

Create `Operator` records in Django admin for your support staff:

```python
from django.contrib.auth import get_user_model
from supchat.models import Operator

User = get_user_model()
user = User.objects.get(username="support_agent")
Operator.objects.create(user=user, is_online=True)
```

### Assigning Operators Programmatically

```python
from supchat.services import assign_operator

# Auto-assign to current user (if they're an operator)
assign_operator(request, conversation)

# Assign to a specific operator
assign_operator(request, conversation, operator=some_operator)
```

### Operator Dashboard

Access the operator panel at `/supchat/operator/` (requires staff permissions).

Features:
- 💬 Real-time conversation list with unread badges
- 📊 Analytics dashboard with 7-day & 30-day charts
- 🎯 Conversation assignment & status management
- 🌓 Dark/Light theme toggle
- 🌐 Bilingual interface (EN/FA)

---

## 🛠️ Public API

The service layer is the stable integration point. Use these functions in your views, signals, or management commands:

```python
from supchat.services import (
    get_or_create_conversation,
    send_message,
    close_conversation,
    assign_operator,
    mark_messages_read,
)
```

### `get_or_create_conversation(request) → (Conversation, guest_id | None)`

Returns an open conversation for the user/guest. Creates one if none exists.

```python
conversation, guest_id = get_or_create_conversation(request)
```

### `send_message(request, conversation, text) → Message`

Sends a message and broadcasts it via SSE.

```python
message = send_message(request, conversation, "Hello!")
```

### `close_conversation(request, conversation) → Conversation`

Closes a conversation (operators only).

```python
close_conversation(request, conversation)
```

### `assign_operator(request, conversation, operator=None) → Conversation`

Assigns an operator to a conversation.

```python
assign_operator(request, conversation, operator=my_operator)
```

### `mark_messages_read(request, conversation, message_ids=None) → int`

Marks messages as read. Returns count of updated messages.

```python
count = mark_messages_read(request, conversation)
```

---

## 🎨 Customization

Override any of these in your project:

```
your_project/
├── templates/
│   └── supchat/
│       └── widget.html          # Override the widget template
└── static/
    └── supchat/
        ├── supchat.css          # Override styles
        └── supchat.js           # Override behavior
```

### CSS Variables

Customize colors by overriding CSS variables:

```css
.supchat-widget {
    --sc-primary: #6366f1;
    --sc-primary-hover: #4f46e5;
    --sc-bubble-user: linear-gradient(135deg, #6366f1, #8b5cf6);
    --sc-bubble-agent: #ffffff;
    --sc-bg: rgba(255, 255, 255, 0.95);
    --sc-fg: #0f172a;
    --sc-border: rgba(226, 232, 240, 0.8);
}
```

### JavaScript Events

Listen to chat events:

```javascript
document.addEventListener('supchat:open', () => {
    console.log('Chat opened');
});

document.addEventListener('supchat:close', () => {
    console.log('Chat closed');
});

document.addEventListener('supchat:message', (e) => {
    console.log('New message:', e.detail);
});
```

---

## 🚢 Deployment

### SSE Requirements

The built-in SSE manager is **process-local** and works great for:
- Development
- Single-process deployments
- Small to medium traffic

For **multi-worker deployments** (Gunicorn, uWSGI with multiple workers), clients connected to different workers won't receive broadcasts. Solutions:

#### Option 1: Single Worker
```bash
gunicorn myproject.wsgi:application --workers 1 --threads 8
```

#### Option 2: Cross-Worker Fanout
Implement your own broadcast mechanism using Redis Pub/Sub, a message queue, or your cache backend:

```python
# myproject/sse_bridge.py
from django.core.cache import cache
from supchat.sse import sse_manager

def broadcast_to_all_workers(conversation_id, event, data):
    # Publish to Redis/cache
    cache.set(f"supchat:broadcast:{conversation_id}", {
        "event": event,
        "data": data,
    }, timeout=5)
    
    # Each worker subscribes and calls:
    # sse_manager.broadcast(conversation_id, event, data)
```

### Proxy Configuration

**Nginx:**
```nginx
location /supchat/ {
    proxy_pass http://localhost:8000;
    proxy_buffering off;              # Critical for SSE
    proxy_cache off;
    proxy_read_timeout 86400s;        # Long timeout for SSE
    proxy_send_timeout 86400s;
}
```

**Apache:**
```apache
<Location /supchat/>
    ProxyPass http://localhost:8000/supchat/
    ProxyPassReverse http://localhost:8000/supchat/
    SetEnv proxy-nokeepalive 1
    SetEnv proxy-sendchunked 1
</Location>
```

---

## 🌐 Browser Support

| Browser | Version |
|---------|---------|
| Chrome | 90+ |
| Firefox | 88+ |
| Safari | 14+ |
| Edge | 90+ |
| iOS Safari | 14+ |
| Android Chrome | 90+ |

---

## 🗺️ Roadmap

- [ ] File/image attachments
- [ ] Message reactions & emoji
- [ ] Conversation tags & categories
- [ ] Canned responses / quick replies
- [ ] Chat transcripts via email
- [ ] Webhook integrations (Slack, Discord)
- [ ] Bot/AI auto-responses
- [ ] Multi-language support (beyond EN/FA)
- [ ] Mobile SDK (iOS/Android)
- [ ] WebSocket adapter (optional)

---

## 🤝 Contributing

Contributions are welcome! Here's how:

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/xo-aria/django-supchat.git
cd django-supchat
pip install -e '.[test]'
pytest
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with ❤️ for the Django community
- Inspired by [Intercom](https://www.intercom.com/), [Crisp](https://crisp.chat/), and [Tawk.to](https://www.tawk.to/)
- Icons from [Lucide](https://lucide.dev/)
- Charts powered by [Chart.js](https://www.chartjs.org/)

---

## 📞 Support

- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/xo-aria/django-supchat/issues)
- 💡 **Feature Requests:** [GitHub Discussions](https://github.com/xo-aria/django-supchat/discussions)
- 📧 **Email:** your-email@example.com

---

<div align="center">

**If django-supchat helps your project, consider giving it a ⭐ on GitHub!**

[⭐ Star on GitHub](https://github.com/xo-aria/django-supchat) • [💬 Join Discussions](https://github.com/xo-aria/django-supchat/discussions)

</div>
