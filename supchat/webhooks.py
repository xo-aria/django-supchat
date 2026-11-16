"""Outgoing webhooks: generic (HMAC signed), Slack and Discord."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from django.utils import timezone

from .conf import supchat_settings
from .models import WebhookEndpoint

log = logging.getLogger("supchat")

EVENTS = (
    "conversation.started",
    "message.created",
    "conversation.closed",
    "conversation.rated",
)


class UnsafeURL(ValueError):
    pass


def check_url(url: str) -> None:
    """SSRF guard: only http(s) and, by default, only public addresses."""
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeURL("Webhook URL must be http(s).")
    if supchat_settings.get("WEBHOOK_ALLOW_PRIVATE"):
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"Cannot resolve {parts.hostname}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeURL("Webhook target resolves to a non-public address.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # redirects could bypass the SSRF check
        return None


def summarize(event: str, data: dict) -> str:
    who = data.get("participant") or "Visitor"
    if event == "conversation.started":
        return f"New support conversation from {who}"
    if event == "message.created":
        return f"{who}: {data.get('text', '')[:300]}"
    if event == "conversation.closed":
        return f"Conversation with {who} was closed"
    if event == "conversation.rated":
        return f"{who} rated the conversation {data.get('rating')}/5"
    return event


def build_request(endpoint: WebhookEndpoint, event: str, data: dict) -> tuple[bytes, dict]:
    headers = {"Content-Type": "application/json", "User-Agent": "django-supchat"}
    if endpoint.kind == WebhookEndpoint.Kind.SLACK:
        body = {"text": summarize(event, data)}
    elif endpoint.kind == WebhookEndpoint.Kind.DISCORD:
        body = {"content": summarize(event, data)[:1900]}
    else:
        body = {"event": event, "data": data, "ts": int(time.time())}
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    if endpoint.kind == WebhookEndpoint.Kind.GENERIC and endpoint.secret:
        sig = hmac.new(endpoint.secret.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Supchat-Signature"] = f"sha256={sig}"
    headers["X-Supchat-Event"] = event
    return raw, headers


def _send(url: str, raw: bytes, headers: dict, timeout: float) -> int:
    check_url(url)
    req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def deliver(endpoint: WebhookEndpoint, event: str, data: dict) -> int | None:
    raw, headers = build_request(endpoint, event, data)
    status, error = None, ""
    try:
        status = _send(endpoint.url, raw, headers, float(supchat_settings.get("WEBHOOK_TIMEOUT")))
        if status >= 400:
            error = f"HTTP {status}"
    except Exception as exc:
        error = str(exc)[:300]
        log.warning("supchat webhook %s failed: %s", endpoint.pk, error)
    WebhookEndpoint.objects.filter(pk=endpoint.pk).update(last_status=status, last_error=error, last_at=timezone.now())
    return status


def dispatch(event: str, data: dict) -> int:
    count = 0
    for endpoint in WebhookEndpoint.objects.filter(is_active=True):
        if endpoint.wants(event):
            deliver(endpoint, event, data)
            count += 1
    return count
