from __future__ import annotations

import hashlib

from django.conf import settings
from django.core import signing
from django.http import HttpRequest

from .conf import supchat_settings
from .models import BlockedVisitor, Conversation, Operator

_GUEST_SALT = "supchat.guest"


def sign_guest_id(guest_id: str) -> str:
    return signing.dumps(guest_id, salt=_GUEST_SALT)


def unsign_guest_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        value = signing.loads(
            token,
            salt=_GUEST_SALT,
            max_age=int(supchat_settings.get("GUEST_COOKIE_AGE")),
        )
    except signing.BadSignature:
        return None
    return value if isinstance(value, str) and len(value) <= 64 else None


def has_header_token(request: HttpRequest) -> bool:
    return bool(request.META.get(supchat_settings.get("GUEST_HEADER")))


def get_request_guest_id(request: HttpRequest) -> str | None:
    """Guest identity from the signed cookie, or the signed header for mobile clients."""
    guest = unsign_guest_token(request.COOKIES.get(supchat_settings.get("GUEST_COOKIE_NAME")))
    if guest:
        return guest
    return unsign_guest_token(request.META.get(supchat_settings.get("GUEST_HEADER")))


def client_ip(request: HttpRequest) -> str:
    if supchat_settings.get("TRUST_PROXY_HEADERS"):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR", "unknown")


def hash_ip(request: HttpRequest) -> str:
    """Salted hash so we can rate-limit / block without storing raw IPs."""
    raw = f"{settings.SECRET_KEY}:{client_ip(request)}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def is_blocked(request: HttpRequest, guest_id: str | None = None) -> bool:
    guest_id = guest_id or get_request_guest_id(request)
    qs = BlockedVisitor.objects.all()
    ip = hash_ip(request)
    from django.db.models import Q

    cond = Q(ip_hash=ip)
    if guest_id:
        cond |= Q(guest_id=guest_id)
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        cond |= Q(user_id=user.pk)
    return qs.filter(cond).exists()


def is_operator_user(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and Operator.objects.filter(user=user).exists())


def is_staff_user(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and (getattr(user, "is_staff", False) or is_operator_user(user)))


def get_operator_for_user(user) -> Operator | None:
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.supchat_operator
    except Operator.DoesNotExist:
        return None


def can_access_conversation(request: HttpRequest, conversation: Conversation) -> bool:
    user = request.user
    if getattr(user, "is_authenticated", False):
        if conversation.user_id == user.pk:
            return True
        if getattr(user, "is_staff", False) or is_operator_user(user):
            return True
    guest_id = get_request_guest_id(request)
    return bool(guest_id and conversation.guest_id and guest_id == conversation.guest_id)


def can_send_message(request: HttpRequest, conversation: Conversation) -> bool:
    return conversation.status == Conversation.Status.OPEN and can_access_conversation(request, conversation)


def can_close_conversation(request: HttpRequest, conversation: Conversation) -> bool:
    return can_access_conversation(request, conversation)


def can_assign_operator(request: HttpRequest, conversation: Conversation) -> bool:
    return is_staff_user(request.user)
