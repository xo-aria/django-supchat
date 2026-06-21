from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


DEFAULTS: dict[str, Any] = {
    "TITLE": "Support",
    "POSITION": "right",  # "right" or "left"
    "THEME": "auto",  # "auto", "light", "dark"
    "ALLOW_GUEST": True,
    "MAX_MESSAGE_LENGTH": 2000,
    "GUEST_COOKIE_NAME": "supchat_guest",
    "GUEST_COOKIE_AGE": 60 * 60 * 24 * 365,
    "HEARTBEAT_INTERVAL": 25,
    "SSE_RETRY_MS": 5000,
    "RATE_LIMIT": {"MESSAGES": 30, "WINDOW": 60},
    "RATE_LIMIT_CALLBACK": None,
}


@dataclass(frozen=True)
class SupchatSettings:
    """Small settings wrapper with explicit defaults and clear errors."""

    def as_dict(self) -> dict[str, Any]:
        configured = getattr(settings, "SUPCHAT", {}) or {}
        if not isinstance(configured, dict):
            raise TypeError("SUPCHAT setting must be a dictionary.")
        merged = {**DEFAULTS, **configured}
        if merged["POSITION"] not in {"left", "right"}:
            raise ValueError('SUPCHAT["POSITION"] must be "left" or "right".')
        if merged["THEME"] not in {"auto", "light", "dark"}:
            raise ValueError('SUPCHAT["THEME"] must be "auto", "light", or "dark".')
        if int(merged["MAX_MESSAGE_LENGTH"]) < 1:
            raise ValueError('SUPCHAT["MAX_MESSAGE_LENGTH"] must be positive.')
        return merged

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)


supchat_settings = SupchatSettings()
