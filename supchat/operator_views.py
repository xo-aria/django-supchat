# views.py
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Conversation, Message, Operator
from .permissions import get_operator_for_user
from .services import (
    assign_operator,
    close_conversation,
    get_conversation_for_request,
    mark_messages_read,
    send_message,
    serialize_message,
    set_operator_online,
    _sender_type_for_request
)
from .sse import streaming_response, sse_manager


def _require_operator(request: HttpRequest) -> Operator:
    if not getattr(request.user, "is_authenticated", False):
        raise PermissionDenied("Login required.")
    operator = get_operator_for_user(request.user)
    if operator is None and not request.user.is_staff:
        raise PermissionDenied("Operator access required.")
    return operator


def _get_chart_data(days=7):
    now = timezone.now()
    start = now - timedelta(days=days - 1)

    daily_stats = (
        Conversation.objects
        .filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    labels = []
    values = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).date()
        labels.append(d.strftime("%a"))
        found = next((s["total"] for s in daily_stats if s["day"] == d), 0)
        values.append(found)

    return labels, values


def _get_sidebar_context(request: HttpRequest):
    operator = _require_operator(request)
    set_operator_online(operator)

    now = timezone.now()
    conversations = (
        Conversation.objects
        .select_related("user", "assigned_operator__user")
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_read=False) & ~Q(messages__sender_type="operator"),
            ),
        )
        .order_by("-last_message_at", "-created_at")
    )

    open_count = conversations.filter(status=Conversation.Status.OPEN).count()
    closed_count = conversations.filter(status=Conversation.Status.CLOSED).count()
    total_count = conversations.count()

    online_operators = Operator.objects.filter(
        is_online=True,
        last_seen__gte=now - timedelta(minutes=5),
    ).select_related("user")

    return {
        "conversations": conversations,
        "open_count": open_count,
        "closed_count": closed_count,
        "total_count": total_count,
        "online_operators": online_operators,
        "current_operator": operator,
    }


@staff_member_required
def dashboard_view(request: HttpRequest):
    context = _get_sidebar_context(request)
    context["active_page"] = "dashboard"
    return render(request, "supchat/operator/dashboard.html", context)


@staff_member_required
def dashboard_partial(request: HttpRequest):
    context = _get_sidebar_context(request)
    context["active_page"] = "dashboard"

    now = timezone.now()
    context["today_count"] = Conversation.objects.filter(created_at__date=now.date()).count()
    context["messages_today"] = Message.objects.filter(created_at__date=now.date()).count()

    return render(request, "supchat/operator/partials/dashboard_content.html", context)


@staff_member_required
def conversation_detail_view(request: HttpRequest, conversation_id):
    _require_operator(request)
    try:
        conversation = (
            Conversation.objects
            .select_related("user", "assigned_operator__user")
            .get(pk=conversation_id)
        )
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Conversation not found."}, status=404)

    messages = (
        Message.objects
        .filter(conversation=conversation)
        .select_related("sender_user")
        .order_by("created_at")
    )

    mark_messages_read(request, conversation)

    data = {
        "ok": True,
        "conversation": {
            "id": str(conversation.pk),
            "status": conversation.status,
            "participant": str(conversation.user) if conversation.user else f"Guest {conversation.guest_id[:8] if conversation.guest_id else '-'}",
            "assigned_operator": str(conversation.assigned_operator.user) if conversation.assigned_operator else None,
            "created_at": conversation.created_at.isoformat(),
            "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
            "message_count": messages.count(),
        },
        "messages": [serialize_message(m) for m in messages],
    }
    return JsonResponse(data)


@staff_member_required
@require_POST
def operator_send_message(request: HttpRequest, conversation_id):
    _require_operator(request)
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Conversation not found."}, status=404)

    try:
        body = json.loads(request.body.decode(request.encoding or "utf-8"))
        text = body.get("text", "").strip()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    if not text:
        return JsonResponse({"ok": False, "error": "Message cannot be empty."}, status=400)

    try:
        message = send_message(request, conversation, text)
    except PermissionDenied as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)

    return JsonResponse({"ok": True, "message": serialize_message(message)}, status=201)


@staff_member_required
@require_POST
def operator_close_conversation(request: HttpRequest, conversation_id):
    _require_operator(request)
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
        close_conversation(request, conversation)
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Conversation not found."}, status=404)
    except PermissionDenied as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)

    return JsonResponse({"ok": True, "status": conversation.status})


@staff_member_required
@require_POST
def operator_delete_conversation(request: HttpRequest, conversation_id):
    _require_operator(request)
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Conversation not found."}, status=404)

    conversation.messages.all().delete()
    conversation.delete()
    return JsonResponse({"ok": True, "deleted": True})


@staff_member_required
@require_POST
def operator_assign(request: HttpRequest, conversation_id):
    _require_operator(request)
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Conversation not found."}, status=404)

    try:
        body = json.loads(request.body.decode(request.encoding or "utf-8"))
        operator_id = body.get("operator_id")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    operator = None
    if operator_id:
        try:
            operator = Operator.objects.get(pk=operator_id)
        except Operator.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Operator not found."}, status=404)

    try:
        assign_operator(request, conversation, operator)
    except PermissionDenied as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=403)

    return JsonResponse({"ok": True})


@staff_member_required
def operator_events(request: HttpRequest, conversation_id):
    _require_operator(request)
    return streaming_response(str(conversation_id))


@staff_member_required
def conversation_list_api(request: HttpRequest):
    _require_operator(request)
    conversations = (
        Conversation.objects
        .select_related("user", "assigned_operator__user")
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(messages__is_read=False) & ~Q(messages__sender_type="operator"),
            ),
        )
        .order_by("-last_message_at", "-created_at")[:50]
    )

    data = []
    for conv in conversations:
        last_msg = conv.messages.order_by("-created_at").first()
        data.append({
            "id": str(conv.pk),
            "status": conv.status,
            "participant": str(conv.user) if conv.user else f"Guest {conv.guest_id[:8] if conv.guest_id else '-'}",
            "assigned_operator": str(conv.assigned_operator.user) if conv.assigned_operator else None,
            "unread_count": conv.unread_count,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "last_message_preview": (last_msg.text[:80] + "...") if last_msg and len(last_msg.text) > 80 else (last_msg.text if last_msg else ""),
        })

    return JsonResponse({"ok": True, "conversations": data})

@staff_member_required
@require_POST
def typing_view(request: HttpRequest, conversation_id):
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)

    try:
        body = json.loads(request.body.decode(request.encoding or "utf-8"))
        is_typing = bool(body.get("is_typing", False))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    sender_type = _sender_type_for_request(request)
    event_type = "typing.start" if is_typing else "typing.stop"
    
    sse_manager.broadcast(str(conversation.pk), event_type, {
        "conversation": str(conversation.pk),
        "sender_type": sender_type
    })
    return JsonResponse({"ok": True})


@require_POST
def read_view(request: HttpRequest, conversation_id):
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)
    
    count = mark_messages_read(request, conversation)
    return JsonResponse({"ok": True, "read": count})
