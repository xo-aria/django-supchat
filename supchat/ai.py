"""AI auto-replies.

Providers (all plain HTTPS via the standard library, zero dependencies):

* ``openai``     - any OpenAI-compatible Chat Completions API (OpenAI/ChatGPT, Azure
                   OpenAI, Groq, OpenRouter, Together, Mistral, DeepSeek, Ollama,
                   LM Studio, vLLM ...). Point ``BASE_URL`` at the host.
* ``anthropic``  - the Anthropic Messages API.
* ``custom``     - a dotted path to ``fn(messages, conversation) -> str`` for anything else.

The bot answers visitor messages only while ``conversation.ai_enabled`` is true. It stops
for good as soon as an operator replies (or the visitor asks for a human).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.utils.module_loading import import_string

from .conf import supchat_settings
from .models import Conversation, Message

log = logging.getLogger("supchat")

OPENAI_URL = "https://api.openai.com/v1"
ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class AIError(Exception):
    pass


def is_enabled() -> bool:
    cfg = supchat_settings.ai()
    return bool(cfg.get("ENABLED"))


def build_messages(conversation: Conversation, limit: int) -> list[dict]:
    """Chat history as role/content pairs. Internal notes are never sent to a provider."""
    qs = (
        Message.objects.filter(conversation=conversation, is_internal=False)
        .exclude(sender_type=Message.SenderType.SYSTEM)
        .order_by("-created_at", "-id")[:limit]
    )
    out: list[dict] = []
    for m in reversed(list(qs)):
        text = m.text or (f"[attachment: {m.attachment_name}]" if m.attachment_name else "")
        if not text:
            continue
        role = "user" if m.sender_type in (Message.SenderType.USER, Message.SenderType.GUEST) else "assistant"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _http_post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - admin-configured URL
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AIError(f"provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIError(f"provider call failed: {type(exc).__name__}") from exc


def call_openai(cfg: dict, messages: list[dict]) -> str:
    base = (cfg.get("BASE_URL") or OPENAI_URL).rstrip("/")
    headers = {"Content-Type": "application/json"}
    if cfg.get("API_KEY"):
        headers["Authorization"] = f"Bearer {cfg['API_KEY']}"
    body = {
        "model": cfg["MODEL"],
        "messages": [{"role": "system", "content": cfg["SYSTEM_PROMPT"]}, *messages],
        cfg.get("TOKEN_PARAM") or "max_tokens": int(cfg["MAX_TOKENS"]),
        **(cfg.get("EXTRA_BODY") or {}),
    }
    data = _http_post(f"{base}/chat/completions", headers, body, float(cfg["TIMEOUT"]))
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("unexpected response shape") from exc


def call_anthropic(cfg: dict, messages: list[dict]) -> str:
    base = (cfg.get("BASE_URL") or ANTHROPIC_URL).rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.get("API_KEY", ""),
        "anthropic-version": ANTHROPIC_VERSION,
    }
    body = {
        "model": cfg["MODEL"],
        "max_tokens": int(cfg["MAX_TOKENS"]),
        "system": cfg["SYSTEM_PROMPT"],
        "messages": messages,
        **(cfg.get("EXTRA_BODY") or {}),
    }
    data = _http_post(f"{base}/v1/messages", headers, body, float(cfg["TIMEOUT"]))
    if data.get("stop_reason") == "refusal":
        raise AIError("provider declined to answer")
    try:
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
    except (KeyError, TypeError) as exc:
        raise AIError("unexpected response shape") from exc


def call_custom(cfg: dict, messages: list[dict], conversation: Conversation) -> str:
    path = cfg.get("CALLABLE")
    if not path:
        raise AIError("AI.CALLABLE is required for PROVIDER='custom'")
    fn = import_string(path) if isinstance(path, str) else path
    return str(fn(messages, conversation) or "").strip()


def generate_reply(conversation: Conversation) -> str:
    cfg = supchat_settings.ai()
    messages = build_messages(conversation, int(cfg["MAX_HISTORY"]))
    if not messages:
        return ""
    provider = cfg["PROVIDER"]
    if provider == "custom":
        return call_custom(cfg, messages, conversation)
    if not cfg.get("MODEL"):
        raise AIError("AI.MODEL is not configured")
    if provider == "anthropic":
        return call_anthropic(cfg, messages)
    if provider == "openai":
        return call_openai(cfg, messages)
    raise AIError(f"unknown provider {provider!r}")


def wants_human(text: str) -> bool:
    low = (text or "").lower()
    return any(k.lower() in low for k in supchat_settings.ai().get("HANDOFF_KEYWORDS", []))


def maybe_auto_reply(conversation_id, trigger_message_id) -> Message | None:
    """Entry point run in the background after a visitor message commits."""
    from .services import post_bot_message, set_bot_typing  # local import: avoid cycle

    if not is_enabled():
        return None
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
        trigger = Message.objects.get(pk=trigger_message_id)
    except (Conversation.DoesNotExist, Message.DoesNotExist):
        return None
    if conversation.status != Conversation.Status.OPEN or not conversation.ai_enabled:
        return None
    if trigger.sender_type not in (Message.SenderType.USER, Message.SenderType.GUEST) or trigger.is_internal:
        return None  # bot messages / operator messages never trigger the bot (no loops)
    if conversation.messages.filter(sender_type=Message.SenderType.OPERATOR, is_internal=False).exists():
        Conversation.objects.filter(pk=conversation.pk).update(ai_enabled=False)
        return None
    if wants_human(trigger.text):
        Conversation.objects.filter(pk=conversation.pk).update(ai_enabled=False)
        return post_bot_message(conversation, supchat_settings.get("HANDOFF_REPLY"), handoff=True)
    set_bot_typing(conversation, True)
    try:
        text = generate_reply(conversation)
    except Exception as exc:  # AIError or a broken custom callable: log without secrets
        log.warning("supchat AI reply failed: %s", exc)
        return None
    finally:
        set_bot_typing(conversation, False)
    if not text:
        return None
    return post_bot_message(conversation, text[: int(supchat_settings.get("MAX_MESSAGE_LENGTH"))])
