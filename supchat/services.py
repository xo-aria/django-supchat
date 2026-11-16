# services.py - the stable public API of django-supchat
from __future__ import annotations

import re
import uuid
from typing import Iterable

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from . import attachments, tasks, webhooks
from .conf import supchat_settings
from .models import BlockedVisitor, Conversation, Message, Operator, Reaction, Tag
from .permissions import (
    can_access_conversation,
    can_assign_operator,
    can_close_conversation,
    can_send_message,
    client_ip,
    get_operator_for_user,
    get_request_guest_id,
    hash_ip,
    is_blocked,
    is_staff_user,
    sign_guest_id,
)
from .signals import (
    conversation_closed,
    conversation_rated,
    conversation_started,
    message_created,
    messages_read,
    operator_offline,
    operator_online,
)
from .sse import sse_manager

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ALLOWED_REACTIONS = ("👍", "❤️", "😂", "😮", "😢", "🙏", "🔥", "🎉")


class RateLimitExceeded(PermissionDenied):
    pass


# --------------------------------------------------------------------- text
def sanitize_message_text(text: str, allow_empty: bool = False) -> str:
    if not isinstance(text, str):
        raise ValidationError("Message text must be a string.")
    text = strip_tags(text)
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    max_length = int(supchat_settings.get("MAX_MESSAGE_LENGTH"))
    if not text and not allow_empty:
        raise ValidationError("Message text cannot be empty.")
    if len(text) > max_length:
        raise ValidationError(f"Message text cannot exceed {max_length} characters.")
    low = text.lower()
    for word in supchat_settings.get("BLOCKED_WORDS") or []:
        if word and word.lower() in low:
            raise ValidationError("Your message contains words that are not allowed.")
    return text


# -------------------------------------------------------------- rate limits
def _client_key(request: HttpRequest) -> str:
    if getattr(request.user, "is_authenticated", False):
        return f"u:{request.user.pk}"
    guest = get_request_guest_id(request)
    if guest:
        return f"g:{guest}"
    return f"ip:{client_ip(request)}"


def check_rate_limit(request: HttpRequest, action: str = "message", limit: int | None = None, window: int | None = None) -> None:
    callback = supchat_settings.get("RATE_LIMIT_CALLBACK")
    if callback:
        if not callback(request=request, action=action):
            raise RateLimitExceeded("Rate limit exceeded.")
        return
    config = supchat_settings.get("RATE_LIMIT") or {}
    limit = int(config.get("MESSAGES", 30)) if limit is None else limit
    window = int(config.get("WINDOW", 60)) if window is None else window
    if limit <= 0:
        return
    key = f"supchat:rl:{action}:{_client_key(request)}"
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=window)
    if count > limit:
        raise RateLimitExceeded("Rate limit exceeded.")


# ------------------------------------------------------------- conversations
def create_guest_id() -> str:
    return uuid.uuid4().hex


def set_guest_cookie(response: HttpResponse, guest_id: str) -> None:
    from django.conf import settings

    response.set_cookie(
        supchat_settings.get("GUEST_COOKIE_NAME"),
        sign_guest_id(guest_id),
        max_age=int(supchat_settings.get("GUEST_COOKIE_AGE")),
        httponly=True,
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        samesite="Lax",
    )


def _participant(conversation: Conversation) -> str:
    return conversation.display_name


def _staff_event(conversation: Conversation, event: str, extra: dict | None = None) -> None:
    sse_manager.broadcast(str(conversation.pk), event, {**serialize_conversation_staff(conversation), **(extra or {})}, internal=True)


def get_or_create_conversation(request: HttpRequest, locale: str = "") -> tuple[Conversation, str | None]:
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    guest_id = None
    if user:
        conversation = Conversation.objects.filter(user=user, status=Conversation.Status.OPEN).order_by("-created_at").first()
    else:
        if not supchat_settings.get("ALLOW_GUEST"):
            raise PermissionDenied("Guest chat is disabled.")
        guest_id = get_request_guest_id(request) or create_guest_id()
        conversation = Conversation.objects.filter(guest_id=guest_id, status=Conversation.Status.OPEN).order_by("-created_at").first()
    if is_blocked(request, guest_id):
        raise PermissionDenied("You are not allowed to start a conversation.")
    if conversation is not None:
        return conversation, guest_id
    ip = hash_ip(request)
    cap = int(supchat_settings.get("MAX_OPEN_PER_IP"))
    if cap and Conversation.objects.filter(ip_hash=ip, status=Conversation.Status.OPEN, messages__isnull=False).distinct().count() >= cap:
        raise RateLimitExceeded("Too many open conversations from this network.")
    conversation = Conversation.objects.create(
        user=user,
        guest_id=guest_id,
        last_message_at=timezone.now(),
        ip_hash=ip,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
        locale=(locale or "")[:8],
    )
    return conversation, guest_id


def conversation_queryset() -> QuerySet[Conversation]:
    return Conversation.objects.select_related("user", "assigned_operator__user")


def get_conversation_for_request(request: HttpRequest, conversation_id) -> Conversation:
    try:
        conversation = conversation_queryset().get(pk=conversation_id)
    except Conversation.DoesNotExist:
        raise PermissionDenied("Conversation not found or not accessible.")
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("Conversation not found or not accessible.")
    return conversation


def _require_staff(request: HttpRequest) -> None:
    if not is_staff_user(request.user):
        raise PermissionDenied("Operator access required.")


def _sender_type_for_request(request: HttpRequest) -> str:
    if get_operator_for_user(request.user):
        return Message.SenderType.OPERATOR
    if getattr(request.user, "is_authenticated", False) and getattr(request.user, "is_staff", False):
        return Message.SenderType.OPERATOR
    if getattr(request.user, "is_authenticated", False):
        return Message.SenderType.USER
    return Message.SenderType.GUEST


def _fire_webhook(event: str, conversation: Conversation, message: Message | None = None) -> None:
    data = {"conversation": str(conversation.pk), "participant": _participant(conversation), "status": conversation.status}
    if message is not None:
        data.update({"message_id": message.pk, "sender_type": message.sender_type, "text": message.text})
    if event == "conversation.rated":
        data["rating"] = conversation.rating
    tasks.run_after_commit(webhooks.dispatch, event, data)


# ------------------------------------------------------------------ messages
@transaction.atomic
def send_message(
    request: HttpRequest,
    conversation: Conversation,
    text: str,
    *,
    upload=None,
    reply_to_id: int | None = None,
    internal: bool = False,
) -> Message:
    if not can_send_message(request, conversation):
        raise PermissionDenied("You cannot send messages to this conversation.")
    staff = is_staff_user(request.user)
    if internal and not staff:
        raise PermissionDenied("Only operators can write internal notes.")
    if not staff and is_blocked(request, conversation.guest_id):
        raise PermissionDenied("You are not allowed to send messages.")
    check_rate_limit(request, "message")
    cap = int(supchat_settings.get("MAX_MESSAGES_PER_CONVERSATION"))
    if cap and not staff and conversation.messages.count() >= cap:
        raise ValidationError("This conversation reached its message limit.")
    sanitized = sanitize_message_text(text or "", allow_empty=upload is not None)
    first_visible = not internal and not conversation.messages.filter(is_internal=False).exists()
    file_info = None
    if upload is not None:
        file_info = attachments.validate_upload(upload)
    reply_to = None
    if reply_to_id:
        reply_to = Message.objects.filter(pk=reply_to_id, conversation=conversation).first()
        if reply_to is None or (reply_to.is_internal and not staff):
            raise ValidationError("The message you are replying to was not found.")
    sender_type = _sender_type_for_request(request)
    message = Message(
        conversation=conversation,
        sender_type=sender_type,
        sender_user=request.user if getattr(request.user, "is_authenticated", False) else None,
        text=sanitized,
        is_internal=internal,
        reply_to=reply_to,
    )
    if file_info:
        name, ext, size = file_info
        message.attachment_name, message.attachment_type, message.attachment_size = name, attachments.mime_for(ext), size
        message.attachment.save(name, upload, save=False)
    message.save()

    now = timezone.now()
    updates = {"updated_at": now}
    if not internal:
        updates["last_message_at"] = now
        conversation.last_message_at = now
        if sender_type == Message.SenderType.OPERATOR:
            updates["ai_enabled"] = False  # a human took over: the bot stays quiet
            conversation.ai_enabled = False
            if conversation.first_response_at is None:
                updates["first_response_at"] = now
                conversation.first_response_at = now
    Conversation.objects.filter(pk=conversation.pk).update(**updates)

    message_created.send(sender=Message, message=message, conversation=conversation)
    payload = serialize_message(message)
    sse_manager.broadcast(str(conversation.pk), "message.created", payload, internal=internal)
    if first_visible:
        conversation_started.send(sender=Conversation, conversation=conversation)
        _staff_event(conversation, "conversation.created", {"last_message_preview": message_preview(message)})
        _fire_webhook("conversation.started", conversation)
    if not internal:
        _staff_event(conversation, "conversation.updated", {"last_message_preview": message_preview(message)})
        _fire_webhook("message.created", conversation, message)
        if sender_type in (Message.SenderType.USER, Message.SenderType.GUEST):
            from . import ai

            if ai.is_enabled() and conversation.ai_enabled:
                tasks.run_after_commit(ai.maybe_auto_reply, conversation.pk, message.pk)
    return message


def message_preview(message: Message) -> str:
    if message.text:
        return message.text[:80]
    return f"📎 {message.attachment_name}" if message.attachment_name else ""


def post_bot_message(conversation: Conversation, text: str, handoff: bool = False) -> Message:
    message = Message.objects.create(conversation=conversation, sender_type=Message.SenderType.BOT, text=text)
    now = timezone.now()
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=now, updated_at=now)
    conversation.last_message_at = now
    sse_manager.broadcast(str(conversation.pk), "message.created", serialize_message(message))
    if handoff:
        sse_manager.broadcast(str(conversation.pk), "ai.handoff", {"conversation": str(conversation.pk)}, internal=True)
    _staff_event(conversation, "conversation.updated", {"last_message_preview": message_preview(message)})
    return message


def set_bot_typing(conversation: Conversation, typing: bool) -> None:
    sse_manager.broadcast(
        str(conversation.pk),
        "typing.start" if typing else "typing.stop",
        {"conversation": str(conversation.pk), "sender_type": "bot"},
    )


def broadcast_typing(request: HttpRequest, conversation: Conversation, is_typing: bool) -> None:
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("Not accessible.")
    check_rate_limit(request, "typing", limit=120, window=60)
    sse_manager.broadcast(
        str(conversation.pk),
        "typing.start" if is_typing else "typing.stop",
        {"conversation": str(conversation.pk), "sender_type": _sender_type_for_request(request)},
    )


# ----------------------------------------------------------------- reactions
def _actor(request: HttpRequest) -> tuple[str, str]:
    operator = get_operator_for_user(request.user)
    if operator:
        return f"o:{operator.pk}", f"operator:{operator.pk}"
    if getattr(request.user, "is_authenticated", False):
        return f"u:{request.user.pk}", "visitor"
    guest = get_request_guest_id(request) or ""
    return f"g:{guest}", "visitor"


def reaction_summary(message: Message) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for emoji, actor in message.reactions.order_by("created_at", "id").values_list("emoji", "actor"):
        label = "visitor" if actor[0] in "ug" else f"operator:{actor[2:]}"
        grouped.setdefault(emoji, []).append(label)
    return [{"emoji": e, "count": len(by), "by": by} for e, by in grouped.items()]


@transaction.atomic
def toggle_reaction(request: HttpRequest, conversation: Conversation, message_id: int, emoji: str) -> list[dict]:
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("Not accessible.")
    if emoji not in ALLOWED_REACTIONS:
        raise ValidationError("This reaction is not supported.")
    message = Message.objects.filter(pk=message_id, conversation=conversation).first()
    if message is None or (message.is_internal and not is_staff_user(request.user)):
        raise ValidationError("Message not found.")
    check_rate_limit(request, "reaction", limit=60, window=60)
    key, _label = _actor(request)
    obj, created = Reaction.objects.get_or_create(message=message, emoji=emoji, actor=key)
    if not created:
        obj.delete()
    summary = reaction_summary(message)
    sse_manager.broadcast(
        str(conversation.pk), "reaction.updated", {"conversation": str(conversation.pk), "message_id": message.pk, "reactions": summary},
        internal=message.is_internal,
    )
    return summary


# ---------------------------------------------------------- state transitions
@transaction.atomic
def close_conversation(request: HttpRequest, conversation: Conversation) -> Conversation:
    if not can_close_conversation(request, conversation):
        raise PermissionDenied("You cannot close this conversation.")
    if conversation.status != Conversation.Status.CLOSED:
        conversation.status = Conversation.Status.CLOSED
        conversation.closed_at = timezone.now()
        conversation.save(update_fields=["status", "closed_at", "updated_at"])
        conversation_closed.send(sender=Conversation, conversation=conversation, closed_by=request.user)
        sse_manager.broadcast(str(conversation.pk), "conversation.closed", {"conversation": str(conversation.pk)})
        _staff_event(conversation, "conversation.updated")
        _fire_webhook("conversation.closed", conversation)
    return conversation


@transaction.atomic
def reopen_conversation(request: HttpRequest, conversation: Conversation) -> Conversation:
    _require_staff(request)
    if conversation.status != Conversation.Status.OPEN:
        conversation.status = Conversation.Status.OPEN
        conversation.closed_at = None
        conversation.save(update_fields=["status", "closed_at", "updated_at"])
        sse_manager.broadcast(str(conversation.pk), "conversation.reopened", {"conversation": str(conversation.pk)})
        _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def assign_operator(request: HttpRequest, conversation: Conversation, operator: Operator | None = None) -> Conversation:
    if not can_assign_operator(request, conversation):
        raise PermissionDenied("You cannot assign operators.")
    operator = operator or get_operator_for_user(request.user)
    if operator is None:
        raise ValidationError("No operator is available for assignment.")
    conversation.assigned_operator = operator
    conversation.save(update_fields=["assigned_operator", "updated_at"])
    _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def unassign_operator(request: HttpRequest, conversation: Conversation) -> Conversation:
    _require_staff(request)
    conversation.assigned_operator = None
    conversation.save(update_fields=["assigned_operator", "updated_at"])
    _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def update_conversation(request: HttpRequest, conversation: Conversation, *, subject=None, priority=None, ai_enabled=None) -> Conversation:
    _require_staff(request)
    fields = ["updated_at"]
    if subject is not None:
        conversation.subject = strip_tags(subject)[:120].strip()
        fields.append("subject")
    if priority is not None:
        if priority not in Conversation.Priority.values:
            raise ValidationError("Invalid priority.")
        conversation.priority = priority
        fields.append("priority")
    if ai_enabled is not None:
        conversation.ai_enabled = bool(ai_enabled)
        fields.append("ai_enabled")
    conversation.save(update_fields=fields)
    _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def set_conversation_tags(request: HttpRequest, conversation: Conversation, tag_ids: Iterable[int]) -> Conversation:
    _require_staff(request)
    conversation.tags.set(Tag.objects.filter(pk__in=list(tag_ids)))
    _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def update_visitor_profile(request: HttpRequest, conversation: Conversation, name: str = "", email: str = "") -> Conversation:
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("Not accessible.")
    check_rate_limit(request, "profile", limit=10, window=60)
    name = strip_tags(name or "").strip()[:80]
    email = (email or "").strip()
    if email:
        validate_email(email)
    if conversation.visitor_email and email != conversation.visitor_email:
        raise ValidationError("The email address of a conversation cannot be changed.")
    conversation.visitor_name, conversation.visitor_email = name, email
    conversation.save(update_fields=["visitor_name", "visitor_email", "updated_at"])
    _staff_event(conversation, "conversation.updated")
    return conversation


@transaction.atomic
def rate_conversation(request: HttpRequest, conversation: Conversation, rating: int, comment: str = "") -> Conversation:
    if not can_access_conversation(request, conversation) or is_staff_user(request.user):
        raise PermissionDenied("Only the visitor can rate a conversation.")
    if conversation.rating is not None:
        raise ValidationError("This conversation was already rated.")
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise ValidationError("Rating must be between 1 and 5.")
    conversation.rating = rating
    conversation.rating_comment = strip_tags(comment or "")[:500].strip()
    conversation.save(update_fields=["rating", "rating_comment", "updated_at"])
    conversation_rated.send(sender=Conversation, conversation=conversation, rating=rating)
    _staff_event(conversation, "conversation.updated")
    _fire_webhook("conversation.rated", conversation)
    return conversation


@transaction.atomic
def block_visitor(request: HttpRequest, conversation: Conversation, reason: str = "") -> BlockedVisitor:
    _require_staff(request)
    if not conversation.user_id and not conversation.guest_id and not conversation.ip_hash:
        raise ValidationError("This conversation has no identity to block.")
    blocked = BlockedVisitor.objects.create(
        user_id=conversation.user_id,
        guest_id=conversation.guest_id or "",
        # never block a whole network for one logged-in account
        ip_hash=conversation.ip_hash if not conversation.user_id else "",
        reason=strip_tags(reason)[:200],
        created_by=request.user,
    )
    close_conversation(request, conversation)
    return blocked


@transaction.atomic
def delete_conversation(request: HttpRequest, conversation: Conversation) -> None:
    _require_staff(request)
    for message in conversation.messages.exclude(attachment="").exclude(attachment__isnull=True):
        message.attachment.delete(save=False)
    pk = str(conversation.pk)
    conversation.delete()
    sse_manager.broadcast(pk, "conversation.deleted", {"conversation": pk}, internal=True)


# ---------------------------------------------------------------- read state
@transaction.atomic
def mark_messages_read(request: HttpRequest, conversation: Conversation, message_ids: Iterable[int] | None = None) -> int:
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("You cannot read this conversation.")
    staff = is_staff_user(request.user)
    visitor_side = [Message.SenderType.USER, Message.SenderType.GUEST]
    qs = Message.objects.filter(conversation=conversation, is_read=False)
    if staff:
        qs = qs.filter(sender_type__in=visitor_side)
    else:
        qs = qs.filter(is_internal=False).exclude(sender_type__in=visitor_side)
    if message_ids is not None:
        qs = qs.filter(id__in=list(message_ids))
    ids = list(qs.values_list("id", flat=True))
    count = qs.update(is_read=True)
    if count:
        messages_read.send(sender=Message, conversation=conversation, message_ids=ids, reader=request.user)
        sse_manager.broadcast(str(conversation.pk), "message.read", {"conversation": str(conversation.pk), "message_ids": ids})
    return count


# ----------------------------------------------------------------- operators
def set_operator_online(operator: Operator) -> None:
    operator.mark_online()
    operator_online.send(sender=Operator, operator=operator)
    for conversation in operator.conversations.filter(status=Conversation.Status.OPEN).only("id"):
        sse_manager.broadcast(str(conversation.pk), "operator.online", {"operator": operator.pk})


def set_operator_offline(operator: Operator) -> None:
    operator.mark_offline()
    operator_offline.send(sender=Operator, operator=operator)
    for conversation in operator.conversations.filter(status=Conversation.Status.OPEN).only("id"):
        sse_manager.broadcast(str(conversation.pk), "operator.offline", {"operator": operator.pk})


def operators_online_count() -> int:
    from datetime import timedelta

    return Operator.objects.filter(is_online=True, last_seen__gte=timezone.now() - timedelta(minutes=3)).count()


# --------------------------------------------------------------- serializers
def _sender_name(message: Message) -> str:
    if message.sender_type == Message.SenderType.BOT:
        return supchat_settings.ai().get("BOT_NAME", "Assistant")
    if message.sender_user_id:
        return message.sender_user.get_short_name() or message.sender_user.get_username()
    return "Guest"


def serialize_message(message: Message) -> dict:
    reply = None
    if message.reply_to_id:
        r = message.reply_to
        reply = {"id": r.pk, "text": r.text[:120] or (f"📎 {r.attachment_name}" if r.attachment_name else ""), "sender_type": r.sender_type}
    attachment = None
    if message.attachment_name and message.attachment:
        ext = attachments.extension_of(message.attachment_name)
        attachment = {
            "name": message.attachment_name,
            "type": message.attachment_type,
            "size": message.attachment_size,
            "url": reverse("supchat:attachment", args=[message.pk]),
            "is_image": ext in attachments.IMAGE_EXT,
        }
    return {
        "id": message.pk,
        "conversation": str(message.conversation_id),
        "sender_type": message.sender_type,
        "sender_user": message.sender_user.username if message.sender_user_id else "Guest",
        "sender_name": _sender_name(message),
        "text": message.text,
        "is_read": message.is_read,
        "is_internal": message.is_internal,
        "created_at": message.created_at.isoformat(),
        "reply_to": reply,
        "attachment": attachment,
        "reactions": reaction_summary(message) if message.pk else [],
    }


def serialize_conversation(conversation: Conversation) -> dict:
    """Visitor-safe view of a conversation (no staff-only fields)."""
    return {
        "id": str(conversation.pk),
        "status": conversation.status,
        "assigned_operator": conversation.assigned_operator_id,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        "rating": conversation.rating,
        "visitor_name": conversation.visitor_name,
        "visitor_email": conversation.visitor_email,
        "ai_active": bool(conversation.ai_enabled and supchat_settings.ai().get("ENABLED")),
    }


def serialize_conversation_staff(conversation: Conversation, unread: int | None = None, preview: str | None = None) -> dict:
    op = conversation.assigned_operator
    if preview is None:
        last = conversation.messages.filter(is_internal=False).order_by("-created_at", "-id").first()
        preview = message_preview(last) if last else ""
    if unread is None:
        unread = conversation.messages.filter(is_read=False, sender_type__in=["user", "guest"]).count()
    return {
        "id": str(conversation.pk),
        "status": conversation.status,
        "participant": _participant(conversation),
        "is_guest": conversation.user_id is None,
        "email": conversation.visitor_email or (conversation.user.email if conversation.user_id else ""),
        "subject": conversation.subject,
        "priority": conversation.priority,
        "tags": [{"id": t.pk, "name": t.name, "color": t.color} for t in conversation.tags.all()],
        "assigned_operator": op.pk if op else None,
        "assigned_name": (op.user.get_full_name() or op.user.get_username()) if op else None,
        "ai_enabled": conversation.ai_enabled,
        "rating": conversation.rating,
        "rating_comment": conversation.rating_comment,
        "locale": conversation.locale,
        "unread_count": unread,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        "created_at": conversation.created_at.isoformat(),
        "last_message_preview": preview,
        "user_agent": conversation.user_agent,
    }
