# operator_views.py - JSON API + shell page for the operator panel
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db.models import Avg, Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, ExtractHour, TruncDate
from django.utils.dateparse import parse_datetime
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import transcripts, webhooks
from .conf import LANGUAGES, supchat_settings
from .models import BlockedVisitor, CannedResponse, Conversation, Message, Operator, Tag, WebhookEndpoint
from .permissions import get_operator_for_user, is_staff_user
from .services import (
    ALLOWED_REACTIONS,
    assign_operator,
    block_visitor,
    broadcast_typing,
    check_rate_limit,
    close_conversation,
    delete_conversation,
    mark_messages_read,
    reopen_conversation,
    send_message,
    serialize_conversation_staff,
    serialize_message,
    set_conversation_tags,
    set_operator_online,
    toggle_reaction,
    unassign_operator,
    update_conversation,
)
from .sse import STAFF_CHANNEL, streaming_response

PAGE = 100


# ------------------------------------------------------------------ plumbing
def operator_api(view):
    """JSON-friendly guard: 401 when anonymous, 403 when not staff/operator."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return JsonResponse({"ok": False, "error": "Login required."}, status=401)
        if not is_staff_user(user):
            return JsonResponse({"ok": False, "error": "Operator access required."}, status=403)
        request.supchat_operator = _ensure_operator(request)
        try:
            return view(request, *args, **kwargs)
        except PermissionDenied as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=403)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    return wrapper


def _ensure_operator(request: HttpRequest) -> Operator:
    operator = get_operator_for_user(request.user)
    if operator is None:
        operator = Operator.objects.create(user=request.user, is_online=False)
    return operator


def _body(request: HttpRequest) -> dict:
    if (request.content_type or "").startswith(("multipart/", "application/x-www-form-urlencoded")):
        return request.POST
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode(request.encoding or "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("Invalid JSON request body.")
    if not isinstance(data, dict):
        raise ValidationError("JSON request body must be an object.")
    return data


def _truthy(value) -> bool:
    return value in (True, "true", "1", 1, "on")


def _get_conversation(conversation_id) -> Conversation:
    try:
        return Conversation.objects.select_related("user", "assigned_operator__user").get(pk=conversation_id)
    except Conversation.DoesNotExist:
        raise PermissionDenied("Conversation not found.")


def _not_found(exc: PermissionDenied) -> JsonResponse:
    return JsonResponse({"ok": False, "error": str(exc)}, status=404)


def _display(user) -> str:
    return user.get_full_name() or user.get_username()


# ---------------------------------------------------------------- shell page
@staff_member_required
def dashboard_view(request: HttpRequest, **route) -> HttpResponse:
    operator = _ensure_operator(request)
    set_operator_online(operator)
    return render(request, "supchat/operator/dashboard.html", {"title": supchat_settings.get("TITLE")})


@staff_member_required
def dashboard_partial(request: HttpRequest) -> HttpResponse:  # backwards compatible alias
    return dashboard_view(request)


# ----------------------------------------------------------------- bootstrap
@operator_api
@require_GET
def bootstrap_api(request: HttpRequest) -> JsonResponse:
    me = request.supchat_operator
    cfg = supchat_settings.as_dict()
    return JsonResponse(
        {
            "ok": True,
            "me": {"id": me.pk, "name": _display(request.user), "username": request.user.get_username(), "is_superuser": request.user.is_superuser},
            "operators": [{"id": o.pk, "name": _display(o.user), "online": o.is_online} for o in Operator.objects.select_related("user")],
            "tags": [{"id": t.pk, "name": t.name, "color": t.color} for t in Tag.objects.all()],
            "canned": [{"id": c.pk, "shortcut": c.shortcut, "title": c.title, "text": c.text} for c in CannedResponse.objects.all()],
            "languages": [lang for lang in cfg["LANGUAGES"] if lang in LANGUAGES],
            "reactions": list(ALLOWED_REACTIONS),
            "attachments": {"enabled": bool(cfg["ATTACHMENTS"]), "max_mb": cfg["ATTACHMENT_MAX_MB"]},
            "sound": bool(cfg["SOUND"]),
            "accent": cfg["ACCENT"],
            "title": cfg["TITLE"],
            "ai": {"enabled": bool(cfg["AI"].get("ENABLED")), "provider": cfg["AI"].get("PROVIDER"), "model": cfg["AI"].get("MODEL")},
            "webhooks": [
                {"id": w.pk, "name": w.name, "kind": w.kind, "is_active": w.is_active, "last_status": w.last_status, "last_error": w.last_error}
                for w in WebhookEndpoint.objects.all()
            ]
            if request.user.is_superuser
            else [],
            "blocked": [
                {"id": b.pk, "label": str(b.user) if b.user_id else (b.guest_id[:8] or b.ip_hash[:8]), "reason": b.reason, "created_at": b.created_at.isoformat()}
                for b in BlockedVisitor.objects.all()[:100]
            ],
        }
    )


@operator_api
@require_POST
def heartbeat_api(request: HttpRequest) -> JsonResponse:
    set_operator_online(request.supchat_operator)
    return JsonResponse({"ok": True})


# ------------------------------------------------------------ conversations
def _list_queryset():
    last_text = Message.objects.filter(conversation=OuterRef("pk"), is_internal=False).order_by("-created_at", "-id")
    return (
        Conversation.objects.select_related("user", "assigned_operator__user")
        .prefetch_related("tags")
        .annotate(
            unread=Count("messages", filter=Q(messages__is_read=False, messages__sender_type__in=["user", "guest"]), distinct=True),
            last_text=Subquery(last_text.values("text")[:1]),
            last_file=Subquery(last_text.values("attachment_name")[:1]),
        )
    )


@operator_api
@require_GET
def conversation_list_api(request: HttpRequest) -> JsonResponse:
    # conversations nobody wrote in yet (widget opened, nothing sent) stay out of the inbox
    qs = _list_queryset().filter(Exists(Message.objects.filter(conversation=OuterRef("pk"), is_internal=False)))
    status = request.GET.get("status", "open")
    if status in ("open", "closed"):
        qs = qs.filter(status=status)
    assigned = request.GET.get("assigned", "any")
    if assigned == "me":
        qs = qs.filter(assigned_operator=request.supchat_operator)
    elif assigned == "unassigned":
        qs = qs.filter(assigned_operator__isnull=True)
    if request.GET.get("unread") in ("1", "true"):
        qs = qs.filter(unread__gt=0)
    if request.GET.get("priority") in Conversation.Priority.values:
        qs = qs.filter(priority=request.GET["priority"])
    tag = request.GET.get("tag", "")
    if tag.isdigit():
        qs = qs.filter(tags__pk=int(tag))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(visitor_name__icontains=q)
            | Q(visitor_email__icontains=q)
            | Q(subject__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(messages__text__icontains=q)
        ).distinct()
    try:
        limit = max(1, min(int(request.GET.get("limit", 40)), 200))
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        limit, offset = 40, 0
    # keyset pagination: stable while new messages reorder the inbox (offsets would skip/duplicate rows)
    qs = qs.annotate(ts=Coalesce("last_message_at", "created_at")).order_by("-ts", "-id")
    cursor = request.GET.get("cursor", "")
    if cursor:
        ts_raw, _, cid = cursor.partition("~")
        ts = parse_datetime(ts_raw)
        try:
            cid = uuid.UUID(cid)
        except ValueError:
            ts = None
        if ts is None:
            raise ValidationError("Invalid cursor.")
        qs = qs.filter(Q(ts__lt=ts) | Q(ts=ts, id__lt=cid))
        offset = 0
    rows = list(qs[offset : offset + limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = f"{rows[-1].ts.isoformat()}~{rows[-1].pk}" if has_more and rows else None
    data = []
    for c in rows:
        preview = c.last_text or (f"📎 {c.last_file}" if c.last_file else "")
        data.append(serialize_conversation_staff(c, unread=c.unread, preview=preview[:80]))
    counts = Conversation.objects.filter(Exists(Message.objects.filter(conversation=OuterRef("pk"), is_internal=False))).aggregate(
        open=Count("pk", filter=Q(status="open")),
        closed=Count("pk", filter=Q(status="closed")),
        mine=Count("pk", filter=Q(status="open", assigned_operator=request.supchat_operator)),
        unassigned=Count("pk", filter=Q(status="open", assigned_operator__isnull=True)),
    )
    counts["unread"] = Message.objects.filter(is_read=False, sender_type__in=["user", "guest"], conversation__status="open").values("conversation").distinct().count()
    return JsonResponse({"ok": True, "conversations": data, "counts": counts, "has_more": has_more, "next_cursor": next_cursor})


@operator_api
@require_GET
def conversation_detail_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    qs = Message.objects.filter(conversation=conversation).select_related("sender_user", "reply_to")
    before = request.GET.get("before", "")
    if before.isdigit():
        qs = qs.filter(pk__lt=int(before))
    page = list(qs.order_by("-id")[: PAGE + 1])
    has_more = len(page) > PAGE
    page = list(reversed(page[:PAGE]))
    if not before:
        mark_messages_read(request, conversation)
    return JsonResponse(
        {
            "ok": True,
            "conversation": {**serialize_conversation_staff(conversation), "message_count": conversation.messages.count()},
            "messages": [serialize_message(m) for m in page],
            "has_more": has_more,
        }
    )


@operator_api
@require_POST
def operator_send_message(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    data = _body(request)
    upload = request.FILES.get("file")
    reply_to = data.get("reply_to")
    message = send_message(
        request,
        conversation,
        str(data.get("text", "")),
        upload=upload,
        reply_to_id=int(reply_to) if str(reply_to or "").isdigit() else None,
        internal=_truthy(data.get("internal")),
    )
    return JsonResponse({"ok": True, "message": serialize_message(message)}, status=201)


def _simple_action(request, conversation_id, fn, **extra):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    fn(request, conversation)
    return JsonResponse({"ok": True, "status": conversation.status, **extra})


@operator_api
@require_POST
def operator_close_conversation(request, conversation_id):
    return _simple_action(request, conversation_id, close_conversation)


@operator_api
@require_POST
def operator_reopen_conversation(request, conversation_id):
    return _simple_action(request, conversation_id, reopen_conversation)


@operator_api
@require_POST
def operator_delete_conversation(request, conversation_id):
    return _simple_action(request, conversation_id, delete_conversation, deleted=True)


@operator_api
@require_POST
def operator_assign(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    data = _body(request)
    if "operator_id" not in data:
        assign_operator(request, conversation)  # assign to myself
        return JsonResponse({"ok": True})
    operator_id = data["operator_id"]
    if operator_id in (None, ""):
        unassign_operator(request, conversation)
        return JsonResponse({"ok": True})
    try:
        operator = Operator.objects.get(pk=operator_id)
    except (Operator.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Operator not found."}, status=404)
    assign_operator(request, conversation, operator)
    return JsonResponse({"ok": True})


@operator_api
@require_POST
def operator_update(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    data = _body(request)
    update_conversation(
        request,
        conversation,
        subject=data.get("subject"),
        priority=data.get("priority"),
        ai_enabled=_truthy(data["ai_enabled"]) if "ai_enabled" in data else None,
    )
    return JsonResponse({"ok": True, "conversation": serialize_conversation_staff(conversation)})


@operator_api
@require_POST
def operator_tags(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    ids = _body(request).get("tag_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise ValidationError("tag_ids must be a list of integers.")
    set_conversation_tags(request, conversation, ids)
    return JsonResponse({"ok": True, "conversation": serialize_conversation_staff(conversation)})


@operator_api
@require_POST
def operator_block(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    block_visitor(request, conversation, str(_body(request).get("reason", "")))
    return JsonResponse({"ok": True})


@operator_api
@require_POST
def operator_react(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    data = _body(request)
    summary = toggle_reaction(request, conversation, int(data.get("message_id") or 0), str(data.get("emoji", "")))
    return JsonResponse({"ok": True, "reactions": summary})


@operator_api
@require_POST
def typing_view(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    broadcast_typing(request, conversation, _truthy(_body(request).get("is_typing")))
    return JsonResponse({"ok": True})


@operator_api
@require_GET
def operator_transcript(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    text = transcripts.build_transcript(conversation, include_internal=_truthy(request.GET.get("notes")))
    response = HttpResponse(text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="chat-transcript.txt"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@operator_api
@require_POST
def operator_transcript_email(request, conversation_id):
    try:
        conversation = _get_conversation(conversation_id)
    except PermissionDenied as exc:
        return _not_found(exc)
    check_rate_limit(request, "transcript", limit=20, window=3600)
    email = str(_body(request).get("email") or conversation.visitor_email or (conversation.user.email if conversation.user_id else "")).strip()
    if not email:
        raise ValidationError("Please provide an email address.")
    validate_email(email)
    transcripts.send_transcript_email(conversation, email)
    return JsonResponse({"ok": True})


@operator_api
def operator_events(request, conversation_id=None):
    """Single staff firehose: every event of every conversation (audience = staff)."""
    return streaming_response(STAFF_CHANNEL, staff=True, request=request)


# ---------------------------------------------------------- tags & canned
@operator_api
@require_POST
def tag_create(request):
    data = _body(request)
    name = str(data.get("name", "")).strip()[:40]
    color = str(data.get("color", "#3390ec"))
    if not name:
        raise ValidationError("Tag name is required.")
    if len(color) != 7 or not color.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
        raise ValidationError("Invalid color.")
    tag, _ = Tag.objects.get_or_create(name=name, defaults={"color": color})
    return JsonResponse({"ok": True, "tag": {"id": tag.pk, "name": tag.name, "color": tag.color}}, status=201)


@operator_api
@require_POST
def tag_delete(request, tag_id):
    Tag.objects.filter(pk=tag_id).delete()
    return JsonResponse({"ok": True})


@operator_api
@require_POST
def canned_create(request):
    data = _body(request)
    shortcut = str(data.get("shortcut", "")).strip().lower().lstrip("/")
    title = str(data.get("title", "")).strip()[:80] or shortcut
    text = str(data.get("text", "")).strip()[:2000]
    from django.utils.text import slugify

    shortcut = slugify(shortcut, allow_unicode=False)[:40]
    if not shortcut or not text:
        raise ValidationError("Shortcut and text are required.")
    obj, _ = CannedResponse.objects.update_or_create(shortcut=shortcut, defaults={"title": title, "text": text, "created_by": request.user})
    return JsonResponse({"ok": True, "canned": {"id": obj.pk, "shortcut": obj.shortcut, "title": obj.title, "text": obj.text}}, status=201)


@operator_api
@require_POST
def canned_delete(request, canned_id):
    CannedResponse.objects.filter(pk=canned_id).delete()
    return JsonResponse({"ok": True})


@operator_api
@require_POST
def unblock(request, blocked_id):
    BlockedVisitor.objects.filter(pk=blocked_id).delete()
    return JsonResponse({"ok": True})


@operator_api
@require_POST
def webhook_test(request, webhook_id):
    if not request.user.is_superuser:
        raise PermissionDenied("Only superusers can manage webhooks.")
    endpoint = WebhookEndpoint.objects.filter(pk=webhook_id).first()
    if endpoint is None:
        return JsonResponse({"ok": False, "error": "Webhook not found."}, status=404)
    status = webhooks.deliver(endpoint, "message.created", {"conversation": "test", "participant": "Test", "text": "Hello from django-supchat", "status": "open"})
    endpoint.refresh_from_db()
    return JsonResponse({"ok": bool(status and status < 400), "status": status, "error": endpoint.last_error})


# ---------------------------------------------------------------- analytics
@operator_api
@require_GET
def analytics_api(request: HttpRequest) -> JsonResponse:
    try:
        days = max(1, min(int(request.GET.get("days", 7)), 90))
    except ValueError:
        days = 7
    now = timezone.now()
    start = now - timedelta(days=days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_list = [(start + timedelta(days=i)).date() for i in range(days)]

    def per_day(qs, field):
        found = {r["d"]: r["n"] for r in qs.filter(**{f"{field}__gte": start}).annotate(d=TruncDate(field)).values("d").annotate(n=Count("pk"))}
        return [found.get(d, 0) for d in day_list]

    msgs = Message.objects.filter(is_internal=False)
    hours = {r["h"]: r["n"] for r in msgs.filter(created_at__gte=start).annotate(h=ExtractHour("created_at")).values("h").annotate(n=Count("pk"))}
    rated = Conversation.objects.filter(rating__isnull=False)
    frt = Conversation.objects.filter(first_response_at__isnull=False, created_at__gte=start).annotate(delta=F("first_response_at") - F("created_at")).aggregate(avg=Avg("delta"))["avg"]
    return JsonResponse(
        {
            "ok": True,
            "labels": [d.isoformat() for d in day_list],
            "conversations": per_day(Conversation.objects.all(), "created_at"),
            "messages": per_day(msgs, "created_at"),
            "hours": [hours.get(h, 0) for h in range(24)],
            "totals": {
                "conversations": Conversation.objects.filter(created_at__gte=start).count(),
                "messages": msgs.filter(created_at__gte=start).count(),
                "open": Conversation.objects.filter(status="open").count(),
                "closed": Conversation.objects.filter(status="closed").count(),
            },
            "rating": {"average": rated.aggregate(a=Avg("rating"))["a"], "count": rated.count(), "distribution": [rated.filter(rating=i).count() for i in range(1, 6)]},
            "first_response_seconds": frt.total_seconds() if frt else None,
            "top_tags": list(Tag.objects.annotate(n=Count("conversations")).filter(n__gt=0).order_by("-n").values("name", "color", "n")[:6]),
        }
    )
