from __future__ import annotations

import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from .forms import MessageReadForm, SendMessageForm
from .models import Message
from .permissions import can_access_conversation
from .services import (
    close_conversation,
    get_conversation_for_request,
    get_or_create_conversation,
    mark_messages_read,
    send_message,
    serialize_conversation,
    serialize_message,
    set_guest_cookie,
)
from .sse import streaming_response


def _json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode(request.encoding or "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("Invalid JSON request body.")
    if not isinstance(data, dict):
        raise ValidationError("JSON request body must be an object.")
    return data


def _error_response(exc: Exception, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": str(exc)}, status=status)

@csrf_exempt
@require_POST
def start_conversation_view(request: HttpRequest) -> JsonResponse:
    try:
        conversation, guest_id = get_or_create_conversation(request)
    except PermissionDenied as exc:
        return _error_response(exc, 403)
    response = JsonResponse({"ok": True, "conversation": serialize_conversation(conversation)})
    if guest_id:
        set_guest_cookie(response, guest_id)
    return response

@csrf_exempt
@require_http_methods(["GET", "POST"])
def messages_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied as exc:
        return _error_response(exc, 403)

    if request.method == "GET":
        messages = Message.objects.filter(conversation=conversation).select_related("sender_user")[:100]
        return JsonResponse({"ok": True, "messages": [serialize_message(message) for message in messages]})

    try:
        form = SendMessageForm(_json_body(request))
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        message = send_message(request, conversation, form.cleaned_data["text"])
    except (PermissionDenied, ValidationError) as exc:
        return _error_response(exc, 403 if isinstance(exc, PermissionDenied) else 400)
    return JsonResponse({"ok": True, "message": serialize_message(message)}, status=201)

@csrf_exempt
@require_POST
def close_conversation_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        close_conversation(request, conversation)
    except PermissionDenied as exc:
        return _error_response(exc, 403)
    return JsonResponse({"ok": True, "conversation": serialize_conversation(conversation)})

@csrf_exempt
@require_POST
def mark_read_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        form = MessageReadForm(_json_body(request))
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        count = mark_messages_read(request, conversation, form.cleaned_data["message_ids"])
    except (PermissionDenied, ValidationError) as exc:
        return _error_response(exc, 403 if isinstance(exc, PermissionDenied) else 400)
    return JsonResponse({"ok": True, "count": count})

@csrf_exempt
@require_GET
def events_view(request: HttpRequest, conversation_id):
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied:
        raise Http404
    if not can_access_conversation(request, conversation):
        raise Http404
    return streaming_response(str(conversation.pk))
