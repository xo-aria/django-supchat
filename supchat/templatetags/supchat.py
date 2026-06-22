from __future__ import annotations
from django.middleware.csrf import get_token
from django import template
from django.urls import NoReverseMatch, reverse

from supchat.conf import supchat_settings

register = template.Library()


@register.inclusion_tag("supchat/widget.html", takes_context=True)
def supchat(context, **overrides):
    """Render the support chat widget.

    Usage: `{% load supchat %}{% supchat %}`. Keyword overrides such as
    `{% supchat title="Help" position="left" %}` are intentionally small and
    safe; deeper customization should override the template/static files.
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

    try:
        start_url = reverse("supchat:start")
    except NoReverseMatch as exc:
        raise RuntimeError(
            'django-supchat URLs are not installed.'
        ) from exc

    return {
        "request": request,
        "config": config,
        "start_url": start_url,
    }
