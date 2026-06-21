from __future__ import annotations

import re
import uuid
from typing import Iterable

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.html import strip_tags

from .conf import supchat_settings
from .models import Conversation, Message, Operator
from .permissions import (
    can_assign_operator,
    can_close_conversation,
    can_send_message,
    get_operator_for_user,
    get_request_guest_id,
    sign_guest_id,
)
from .signals import conversation_closed, message_created, messages_read, operator_offline, operator_online
from .sse import sse_manager

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class RateLimitExceeded(PermissionDenied):
    pass


def sanitize_message_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValidationError("Message text must be a string.")
    text = strip_tags(text)
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    max_length = int(supchat_settings.get("MAX_MESSAGE_LENGTH"))
    if not text:
        raise ValidationError("Message text cannot be empty.")
    if len(text) > max_length:
        raise ValidationError(f"Message text cannot exceed {max_length} characters.")
    return text


def _client_key(request: HttpRequest) -> str:
    if getattr(request.user, "is_authenticated", False):
        return f"u:{request.user.pk}"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    ip = forwarded or request.META.get("REMOTE_ADDR", "unknown")
    return f"ip:{ip}"


def check_rate_limit(request: HttpRequest, action: str = "message") -> None:
    callback = supchat_settings.get("RATE_LIMIT_CALLBACK")
    if callback:
        allowed = callback(request=request, action=action)
        if not allowed:
            raise RateLimitExceeded("Rate limit exceeded.")
        return
    config = supchat_settings.get("RATE_LIMIT") or {}
    limit = int(config.get("MESSAGES", 30))
    window = int(config.get("WINDOW", 60))
    if limit <= 0:
        return
    key = f"supchat:rl:{action}:{_client_key(request)}"
    count = cache.get(key, 0) + 1
    cache.set(key, count, timeout=window)
    if count > limit:
        raise RateLimitExceeded("Rate limit exceeded.")


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


def get_or_create_conversation(request: HttpRequest) -> tuple[Conversation, str | None]:
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    if user:
        conversation = Conversation.objects.filter(user=user, status=Conversation.Status.OPEN).order_by("-created_at").first()
        if conversation is None:
            conversation = Conversation.objects.create(user=user, last_message_at=timezone.now())
        return conversation, None

    if not supchat_settings.get("ALLOW_GUEST"):
        raise PermissionDenied("Guest chat is disabled.")

    guest_id = get_request_guest_id(request) or create_guest_id()
    conversation = Conversation.objects.filter(guest_id=guest_id, status=Conversation.Status.OPEN).order_by("-created_at").first()
    if conversation is None:
        conversation = Conversation.objects.create(guest_id=guest_id, last_message_at=timezone.now())
    return conversation, guest_id


def conversation_queryset() -> QuerySet[Conversation]:
    return Conversation.objects.select_related("user", "assigned_operator__user")


def get_conversation_for_request(request: HttpRequest, conversation_id) -> Conversation:
    from .permissions import can_access_conversation

    try:
        conversation = conversation_queryset().get(pk=conversation_id)
    except Conversation.DoesNotExist:
        raise PermissionDenied("Conversation not found or not accessible.")
    if not can_access_conversation(request, conversation):
        raise PermissionDenied("Conversation not found or not accessible.")
    return conversation


def _sender_type_for_request(request: HttpRequest) -> str:
    operator = get_operator_for_user(request.user)
    if operator:
        return Message.SenderType.OPERATOR
    if getattr(request.user, "is_authenticated", False):
        return Message.SenderType.USER
    return Message.SenderType.GUEST


@transaction.atomic
def send_message(request: HttpRequest, conversation: Conversation, text: str) -> Message:
    if not can_send_message(request, conversation):
        raise PermissionDenied("You cannot send messages to this conversation.")
    check_rate_limit(request, "message")
    sanitized = sanitize_message_text(text)
    sender_user = request.user if getattr(request.user, "is_authenticated", False) else None
    message = Message.objects.create(
        conversation=conversation,
        sender_type=_sender_type_for_request(request),
        sender_user=sender_user,
        text=sanitized,
    )
    now = timezone.now()
    Conversation.objects.filter(pk=conversation.pk).update(updated_at=now, last_message_at=now)
    conversation.last_message_at = now
    message_created.send(sender=Message, message=message, conversation=conversation)
    sse_manager.broadcast(str(conversation.pk), "message.created", serialize_message(message))
    return message


@transaction.atomic
def close_conversation(request: HttpRequest, conversation: Conversation) -> Conversation:
    if not can_close_conversation(request, conversation):
        raise PermissionDenied("You cannot close this conversation.")
    if conversation.status != Conversation.Status.CLOSED:
        conversation.status = Conversation.Status.CLOSED
        conversation.save(update_fields=["status", "updated_at"])
        conversation_closed.send(sender=Conversation, conversation=conversation, closed_by=request.user)
        sse_manager.broadcast(str(conversation.pk), "conversation.closed", {"conversation": str(conversation.pk)})
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
    return conversation


@transaction.atomic
def mark_messages_read(request: HttpRequest, conversation: Conversation, message_ids: Iterable[int] | None = None) -> int:
    from .permissions import can_access_conversation

    if not can_access_conversation(request, conversation):
        raise PermissionDenied("You cannot read this conversation.")
    qs = Message.objects.filter(conversation=conversation, is_read=False)
    if message_ids is not None:
        qs = qs.filter(id__in=list(message_ids))
    ids = list(qs.values_list("id", flat=True))
    count = qs.update(is_read=True)
    if count:
        messages_read.send(sender=Message, conversation=conversation, message_ids=ids, reader=request.user)
        sse_manager.broadcast(str(conversation.pk), "message.read", {"conversation": str(conversation.pk), "message_ids": ids})
    return count


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


def serialize_message(message: Message) -> dict:
    return {
        "id": message.pk,
        "conversation": str(message.conversation_id),
        "sender_type": message.sender_type,
        "sender_user": message.sender_user_id,
        "text": message.text,
        "is_read": message.is_read,
        "created_at": message.created_at.isoformat(),
    }


def serialize_conversation(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.pk),
        "status": conversation.status,
        "assigned_operator": conversation.assigned_operator_id,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
    }
