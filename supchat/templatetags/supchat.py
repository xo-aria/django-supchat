from __future__ import annotations

import json

from django import template
from django.middleware.csrf import get_token
from django.urls import NoReverseMatch, reverse

from supchat.conf import LANGUAGES, supchat_settings
from supchat.services import ALLOWED_REACTIONS

register = template.Library()


@register.inclusion_tag("supchat/widget.html", takes_context=True)
def supchat(context, **overrides):
    """Render the support chat widget.

    Usage: ``{% load supchat %}{% supchat %}``. Keyword overrides such as
    ``{% supchat title="Help" position="left" theme="dark" language="fa" %}`` are
    intentionally small and safe; deeper customization should override the
    template/static files.
    """
    request = context.get("request")
    if request:
        get_token(request)

    config = supchat_settings.as_dict()

    if overrides.get("title"):
        config["TITLE"] = overrides["title"]
    if overrides.get("position") in {"left", "right"}:
        config["POSITION"] = overrides["position"]
    if overrides.get("theme") in {"auto", "light", "dark"}:
        config["THEME"] = overrides["theme"]
    if overrides.get("language") in set(LANGUAGES) | {"auto"}:
        config["LANGUAGE"] = overrides["language"]

    try:
        start_url = reverse("supchat:start")
        config_url = reverse("supchat:config")
    except NoReverseMatch as exc:
        raise RuntimeError("django-supchat URLs are not installed.") from exc

    public = {
        "startUrl": start_url,
        "configUrl": config_url,
        "title": config["TITLE"],
        "language": config["LANGUAGE"],
        "languages": [lang for lang in config["LANGUAGES"] if lang in LANGUAGES],
        "welcome": config["WELCOME_MESSAGE"],
        "quickReplies": list(config["QUICK_REPLIES"]),
        "prechat": bool(config["PRECHAT_FORM"]),
        "sound": bool(config["SOUND"]),
        "maxLength": int(config["MAX_MESSAGE_LENGTH"]),
        "attachments": bool(config["ATTACHMENTS"]),
        "maxMb": config["ATTACHMENT_MAX_MB"],
        "reactions": list(ALLOWED_REACTIONS),
        "ai": bool(config["AI"].get("ENABLED")),
        "botName": config["AI"].get("BOT_NAME", "Assistant"),
        "accent": config["ACCENT"],
        "theme": config["THEME"],
    }
    return {
        "request": request,
        "config": config,
        "start_url": start_url,
        "config_json": json.dumps(public, ensure_ascii=False),
    }
