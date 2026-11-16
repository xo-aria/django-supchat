from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings

LANGUAGES = ("en", "fa", "ar", "tr", "es", "de", "fr", "ru")

DEFAULTS: dict[str, Any] = {
    # --- widget -----------------------------------------------------------
    "TITLE": "Support",
    "POSITION": "right",  # "right" or "left"
    "THEME": "auto",  # "auto", "light", "dark"
    "ACCENT": "#3390ec",
    "LANGUAGE": "auto",  # "auto" or one of LANGUAGES
    "LANGUAGES": list(LANGUAGES),  # languages offered in the switcher
    "WELCOME_MESSAGE": "",
    "QUICK_REPLIES": [],  # list of short strings shown as chips on an empty chat
    "PRECHAT_FORM": False,  # ask guests for name / email before the first message
    "SOUND": True,
    "ALLOW_GUEST": True,
    "MAX_MESSAGE_LENGTH": 2000,
    # --- identity / transport ---------------------------------------------
    "GUEST_COOKIE_NAME": "supchat_guest",
    "GUEST_COOKIE_AGE": 60 * 60 * 24 * 365,
    "GUEST_HEADER": "HTTP_X_SUPCHAT_GUEST",  # token auth for mobile / non-browser clients
    "TRUST_PROXY_HEADERS": False,  # honour X-Forwarded-For for rate limits / IP hashing
    "HEARTBEAT_INTERVAL": 25,
    "SSE_RETRY_MS": 5000,
    "BACKGROUND": "thread",  # "thread" (default) or "sync" for AI / webhooks / email
    "BROADCAST_HOOK": None,  # dotted path: callable(conversation_id, event, data, internal) for cross-worker fan-out
    # --- safety -----------------------------------------------------------
    "RATE_LIMIT": {"MESSAGES": 30, "WINDOW": 60},
    "RATE_LIMIT_CALLBACK": None,
    "BLOCKED_WORDS": [],  # messages containing any of these are rejected
    "MAX_OPEN_PER_IP": 20,  # 0 disables
    "MAX_MESSAGES_PER_CONVERSATION": 2000,  # 0 disables
    # --- attachments ------------------------------------------------------
    "ATTACHMENTS": True,
    "ATTACHMENT_MAX_MB": 5,
    "ATTACHMENT_EXTENSIONS": ["jpg", "jpeg", "png", "gif", "webp", "pdf", "txt", "zip", "docx", "xlsx"],
    # --- lifecycle --------------------------------------------------------
    "HANDOFF_REPLY": "I've notified our team. A human will reply as soon as possible.",
    "AUTO_CLOSE_AFTER_HOURS": 0,  # used by `manage.py supchat_cleanup`
    "RETENTION_DAYS": 0,  # delete closed conversations older than this; 0 keeps forever
    # --- transcripts ------------------------------------------------------
    "TRANSCRIPT_EMAIL_FROM": None,
    "TRANSCRIPT_RATE_LIMIT": {"COUNT": 3, "WINDOW": 3600},
    # --- webhooks ---------------------------------------------------------
    "WEBHOOK_TIMEOUT": 5,
    "WEBHOOK_ALLOW_PRIVATE": False,  # SSRF guard: block private/loopback targets
    # --- AI auto reply ----------------------------------------------------
    "AI": {
        "ENABLED": False,
        "PROVIDER": "openai",  # "openai" (any OpenAI-compatible API), "anthropic", "custom"
        "API_KEY": "",
        "MODEL": "",
        "BASE_URL": "",  # override for OpenAI-compatible hosts (Groq, OpenRouter, Ollama, Azure ...)
        "SYSTEM_PROMPT": "You are a friendly, concise customer support assistant. If you cannot help, say a human will follow up.",
        "MAX_HISTORY": 20,
        "MAX_TOKENS": 1024,
        "TOKEN_PARAM": "max_tokens",  # OpenAI-compatible only; some OpenAI models need "max_completion_tokens"
        "EXTRA_BODY": {},  # merged into every provider request (e.g. temperature, reasoning/effort options)
        "TIMEOUT": 20,
        "CALLABLE": None,  # dotted path for PROVIDER="custom": fn(messages, conversation) -> str
        "HANDOFF_KEYWORDS": ["human", "agent", "operator", "انسان", "اپراتور", "پشتیبان"],
        "BOT_NAME": "Assistant",
    },
}


@dataclass(frozen=True)
class SupchatSettings:
    """Small settings wrapper with explicit defaults and clear errors."""

    def as_dict(self) -> dict[str, Any]:
        configured = getattr(settings, "SUPCHAT", {}) or {}
        if not isinstance(configured, dict):
            raise TypeError("SUPCHAT setting must be a dictionary.")
        merged = {**DEFAULTS, **configured}
        merged["AI"] = {**DEFAULTS["AI"], **(configured.get("AI") or {})}
        if merged["POSITION"] not in {"left", "right"}:
            raise ValueError('SUPCHAT["POSITION"] must be "left" or "right".')
        if merged["THEME"] not in {"auto", "light", "dark"}:
            raise ValueError('SUPCHAT["THEME"] must be "auto", "light", or "dark".')
        if int(merged["MAX_MESSAGE_LENGTH"]) < 1:
            raise ValueError('SUPCHAT["MAX_MESSAGE_LENGTH"] must be positive.')
        if merged["LANGUAGE"] != "auto" and merged["LANGUAGE"] not in LANGUAGES:
            raise ValueError('SUPCHAT["LANGUAGE"] must be "auto" or a supported language code.')
        return merged

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def ai(self) -> dict[str, Any]:
        return self.as_dict()["AI"]


supchat_settings = SupchatSettings()
