# Configuration reference

All options live in one dictionary. Anything you leave out uses the default below.

```python
SUPCHAT = {
    "TITLE": "Support",
    # ...
}
```

## Widget

| Setting | Default | Description |
|---|---|---|
| `TITLE` | `"Support"` | Header title of the widget and the panel. |
| `POSITION` | `"right"` | Screen corner: `"right"` or `"left"`. Stays put in RTL pages. |
| `THEME` | `"auto"` | `"auto"` follows the OS; `"light"` or `"dark"` forces one. Visitors can change it from the menu. |
| `ACCENT` | `"#3390ec"` | Brand color for the launcher, bubbles and buttons (widget and panel). |
| `LANGUAGE` | `"auto"` | `"auto"` uses the visitor's saved choice, then `<html lang>`, then the browser language. Or force one: `"en"`, `"fa"`, `"ar"`, `"tr"`, `"es"`, `"de"`, `"fr"`, `"ru"`. |
| `LANGUAGES` | all 8 | Languages offered in the language switcher (widget and panel). |
| `WELCOME_MESSAGE` | `""` | First bubble shown on an empty chat. Empty means a translated default. It is not stored. |
| `QUICK_REPLIES` | `[]` | Chips on an empty chat, e.g. `["Pricing", "Talk to a human"]`. |
| `PRECHAT_FORM` | `False` | Ask guests for a name and an optional email before the first message. |
| `SOUND` | `True` | Message sounds (each visitor and operator can still mute them). |
| `ALLOW_GUEST` | `True` | Allow anonymous visitors. When `False`, only logged-in users can chat. |
| `MAX_MESSAGE_LENGTH` | `2000` | Maximum characters per message. |

## Identity & transport

| Setting | Default | Description |
|---|---|---|
| `GUEST_COOKIE_NAME` | `"supchat_guest"` | Signed, HttpOnly cookie that identifies a guest. |
| `GUEST_COOKIE_AGE` | 1 year | Cookie and token lifetime in seconds. |
| `GUEST_HEADER` | `"HTTP_X_SUPCHAT_GUEST"` | META key of the header that native clients use instead of the cookie. |
| `TRUST_PROXY_HEADERS` | `False` | Use `X-Forwarded-For` for rate limits and IP hashing. Enable it **only** behind a proxy that sets this header. |
| `HEARTBEAT_INTERVAL` | `25` | Seconds between SSE keep-alive comments. |
| `SSE_RETRY_MS` | `5000` | Reconnect delay sent to `EventSource`. |
| `BROADCAST_HOOK` | `None` | Dotted path to `fn(conversation_id, event, data, internal)`, called on every broadcast, for cross-worker fan-out. See [realtime.md](realtime.md). |
| `BACKGROUND` | `"thread"` | How AI calls, webhooks and email run after commit: `"thread"`, or `"sync"` (useful in tests). |

## Safety

| Setting | Default | Description |
|---|---|---|
| `RATE_LIMIT` | `{"MESSAGES": 30, "WINDOW": 60}` | Messages per window (seconds), per user, per guest identity, or per IP when neither exists. `MESSAGES: 0` disables it. |
| `RATE_LIMIT_CALLBACK` | `None` | `fn(request=..., action=...) -> bool` replaces the built-in limiter. Actions: `message`, `upload`, `typing`, `reaction`, `profile`, `transcript`. |
| `BLOCKED_WORDS` | `[]` | Case-insensitive substrings that reject a message. |
| `MAX_OPEN_PER_IP` | `20` | Open conversations *with messages* allowed per (hashed) IP. `0` disables it. Behind a proxy, enable `TRUST_PROXY_HEADERS`. |
| `MAX_MESSAGES_PER_CONVERSATION` | `2000` | Visitor messages allowed per conversation. `0` disables it. |

## Attachments

| Setting | Default | Description |
|---|---|---|
| `ATTACHMENTS` | `True` | Enable file uploads for visitors and operators. |
| `ATTACHMENT_MAX_MB` | `5` | Maximum size per file. |
| `ATTACHMENT_EXTENSIONS` | `jpg jpeg png gif webp pdf txt zip docx xlsx` | Allowed extensions. SVG, HTML, JS and executables are refused even if listed. |

## Lifecycle

| Setting | Default | Description |
|---|---|---|
| `AUTO_CLOSE_AFTER_HOURS` | `0` | `manage.py supchat_cleanup` closes open conversations idle for longer than this. |
| `RETENTION_DAYS` | `0` | `supchat_cleanup` deletes closed conversations (and their files) older than this. |
| `HANDOFF_REPLY` | *"I've notified our team…"* | Bot message sent when a visitor asks for a human. |

## Transcripts & webhooks

| Setting | Default | Description |
|---|---|---|
| `TRANSCRIPT_EMAIL_FROM` | `DEFAULT_FROM_EMAIL` | Sender address for transcript emails. |
| `TRANSCRIPT_RATE_LIMIT` | `{"COUNT": 3, "WINDOW": 3600}` | Transcript emails per visitor per window. |
| `WEBHOOK_TIMEOUT` | `5` | Seconds per webhook request. |
| `WEBHOOK_ALLOW_PRIVATE` | `False` | Allow webhooks to private or loopback addresses (SSRF guard). |

## AI

```python
SUPCHAT = {
    "AI": {
        "ENABLED": False,
        "PROVIDER": "openai",      # "openai" | "anthropic" | "custom"
        "API_KEY": "",
        "MODEL": "",
        "BASE_URL": "",            # OpenAI-compatible hosts, proxies, Azure ...
        "SYSTEM_PROMPT": "You are a friendly, concise customer support assistant. ...",
        "MAX_HISTORY": 20,         # messages sent as context
        "MAX_TOKENS": 1024,
        "TOKEN_PARAM": "max_tokens",   # OpenAI-compatible only: some models want "max_completion_tokens"
        "EXTRA_BODY": {},              # merged into every request: temperature, effort/reasoning options ...
        "TIMEOUT": 20,
        "CALLABLE": None,          # for PROVIDER="custom"
        "HANDOFF_KEYWORDS": ["human", "agent", "operator", "انسان", "اپراتور", "پشتیبان"],
        "BOT_NAME": "Assistant",
    },
}
```

See [ai.md](ai.md) for details. Keep `API_KEY` in an environment variable, never in source control.

## Per-render overrides

```django
{% supchat title="Help desk" position="left" theme="dark" language="fa" %}
```
