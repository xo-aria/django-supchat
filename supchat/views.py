from __future__ import annotations

import json
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import transcripts
from .conf import LANGUAGES, supchat_settings
from .forms import MessageReadForm, SendMessageForm
from .models import Message
from .permissions import can_access_conversation, has_header_token, is_staff_user, sign_guest_id
from .services import (
    ALLOWED_REACTIONS,
    broadcast_typing,
    check_rate_limit,
    close_conversation,
    get_conversation_for_request,
    get_or_create_conversation,
    mark_messages_read,
    operators_online_count,
    rate_conversation,
    send_message,
    serialize_conversation,
    serialize_message,
    set_guest_cookie,
    toggle_reaction,
    update_visitor_profile,
)
from .sse import streaming_response

PAGE_SIZE = 50


def supchat_csrf(view):
    """CSRF-protect cookie-authenticated requests; header-token (mobile) clients are exempt.

    A browser cannot attach the custom guest header cross-site without a CORS
    preflight, so a request carrying a valid header token cannot be forged by a page.
    """
    protected = csrf_protect(view)

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if has_header_token(request):
            return view(request, *args, **kwargs)
        return protected(request, *args, **kwargs)

    return csrf_exempt(wrapper)


def _json_body(request: HttpRequest) -> dict:
    if (request.content_type or "").startswith(("multipart/", "application/x-www-form-urlencoded")):
        return request.POST.dict()  # form posts (e.g. after CSRF middleware read the stream)
    if not request.body:
        return {}
    is_json = (request.content_type or "").startswith("application/json")
    try:
        data = json.loads(request.body.decode(request.encoding or "utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if not is_json:
            return {}  # e.g. an empty form POST: nothing to read
        raise ValidationError("Invalid JSON request body.")
    if not isinstance(data, dict):
        raise ValidationError("JSON request body must be an object.")
    return data


def _error_response(exc: Exception, status: int = 400) -> JsonResponse:
    msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _fail(exc: Exception) -> JsonResponse:
    return _error_response(exc, 403 if isinstance(exc, PermissionDenied) else 400)


@require_GET
def config_view(request: HttpRequest) -> JsonResponse:
    cfg = supchat_settings.as_dict()
    return JsonResponse(
        {
            "ok": True,
            "title": cfg["TITLE"],
            "languages": [lang for lang in cfg["LANGUAGES"] if lang in LANGUAGES],
            "welcome_message": cfg["WELCOME_MESSAGE"],
            "quick_replies": cfg["QUICK_REPLIES"],
            "prechat_form": bool(cfg["PRECHAT_FORM"]),
            "sound": bool(cfg["SOUND"]),
            "max_message_length": int(cfg["MAX_MESSAGE_LENGTH"]),
            "reactions": list(ALLOWED_REACTIONS),
            "attachments": {
                "enabled": bool(cfg["ATTACHMENTS"]),
                "max_mb": cfg["ATTACHMENT_MAX_MB"],
                "extensions": cfg["ATTACHMENT_EXTENSIONS"],
            },
            "ai": bool(cfg["AI"].get("ENABLED")),
            "operators_online": operators_online_count(),
        }
    )


@supchat_csrf
@require_POST
def start_conversation_view(request: HttpRequest) -> JsonResponse:
    try:
        locale = str(_json_body(request).get("locale", ""))
        conversation, guest_id = get_or_create_conversation(request, locale=locale)
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    body = {"ok": True, "conversation": serialize_conversation(conversation)}
    if guest_id and request.META.get("HTTP_X_SUPCHAT_CLIENT"):
        body["guest_token"] = sign_guest_id(guest_id)  # for native clients; browsers use the HttpOnly cookie
    response = JsonResponse(body)
    if guest_id:
        set_guest_cookie(response, guest_id)
    return response


@supchat_csrf
@require_http_methods(["GET", "POST"])
def messages_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied as exc:
        return _fail(exc)

    if request.method == "GET":
        qs = Message.objects.filter(conversation=conversation, is_internal=False).select_related("sender_user", "reply_to")
        before = request.GET.get("before")
        if before and before.isdigit():
            qs = qs.filter(pk__lt=int(before))
        page = list(qs.order_by("-id")[: PAGE_SIZE + 1])
        has_more = len(page) > PAGE_SIZE
        page = list(reversed(page[:PAGE_SIZE]))
        return JsonResponse({"ok": True, "messages": [serialize_message(m) for m in page], "has_more": has_more})

    try:
        upload = request.FILES.get("file")
        if request.content_type and request.content_type.startswith("multipart/"):
            data = request.POST
        else:
            data = _json_body(request)
        form = SendMessageForm({"text": data.get("text", "")}, allow_empty=upload is not None)
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors, "error": "; ".join(sum(form.errors.values(), []))}, status=400)
        if upload is not None:
            check_rate_limit(request, "upload", limit=10, window=60)
        reply_to = data.get("reply_to")
        message = send_message(
            request,
            conversation,
            form.cleaned_data["text"],
            upload=upload,
            reply_to_id=int(reply_to) if str(reply_to or "").isdigit() else None,
        )
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    return JsonResponse({"ok": True, "message": serialize_message(message)}, status=201)


@supchat_csrf
@require_POST
def close_conversation_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        close_conversation(request, conversation)
    except PermissionDenied as exc:
        return _fail(exc)
    return JsonResponse({"ok": True, "conversation": serialize_conversation(conversation)})


@supchat_csrf
@require_POST
def mark_read_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        form = MessageReadForm(_json_body(request))
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        count = mark_messages_read(request, conversation, form.cleaned_data["message_ids"])
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    return JsonResponse({"ok": True, "count": count})


@supchat_csrf
@require_POST
def react_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        data = _json_body(request)
        summary = toggle_reaction(request, conversation, int(data.get("message_id") or 0), str(data.get("emoji", "")))
    except (PermissionDenied, ValidationError, ValueError) as exc:
        return _fail(exc if not isinstance(exc, ValueError) else ValidationError("Invalid request."))
    return JsonResponse({"ok": True, "reactions": summary})


@supchat_csrf
@require_POST
def rate_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        data = _json_body(request)
        rate_conversation(request, conversation, data.get("rating"), str(data.get("comment", "")))
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    return JsonResponse({"ok": True})


@supchat_csrf
@require_POST
def profile_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        data = _json_body(request)
        update_visitor_profile(request, conversation, str(data.get("name", "")), str(data.get("email", "")))
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    return JsonResponse({"ok": True, "conversation": serialize_conversation(conversation)})


@supchat_csrf
@require_POST
def typing_view(request: HttpRequest, conversation_id) -> JsonResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
        broadcast_typing(request, conversation, bool(_json_body(request).get("is_typing", False)))
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    return JsonResponse({"ok": True})


@require_GET
def transcript_download_view(request: HttpRequest, conversation_id) -> HttpResponse:
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied as exc:
        return _fail(exc)
    response = HttpResponse(transcripts.build_transcript(conversation), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="chat-transcript.txt"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@supchat_csrf
@require_POST
def transcript_email_view(request: HttpRequest, conversation_id) -> JsonResponse:
    """Email the transcript. Sent only to the address the visitor already gave us
    (or their account address) so the endpoint cannot be used as a spam relay."""
    from django.core.validators import validate_email

    try:
        conversation = get_conversation_for_request(request, conversation_id)
        rl = supchat_settings.get("TRANSCRIPT_RATE_LIMIT")
        check_rate_limit(request, "transcript", limit=int(rl["COUNT"]), window=int(rl["WINDOW"]))
        email = conversation.visitor_email or (conversation.user.email if conversation.user_id else "")
        requested = str(_json_body(request).get("email", "")).strip()
        if requested and requested != email:
            validate_email(requested)
            if conversation.visitor_email or conversation.user_id:
                raise ValidationError("Use the email address on this conversation.")
            update_visitor_profile(request, conversation, conversation.visitor_name, requested)
            email = requested
        if not email:
            raise ValidationError("Please provide an email address.")
        transcripts.send_transcript_email(conversation, email)
    except (PermissionDenied, ValidationError) as exc:
        return _fail(exc)
    except OSError:
        return JsonResponse({"ok": False, "error": "Could not send email right now."}, status=502)
    return JsonResponse({"ok": True})


_INLINE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@require_GET
def attachment_view(request: HttpRequest, message_id: int) -> HttpResponse:
    message = Message.objects.select_related("conversation").filter(pk=message_id).first()
    if message is None or not message.attachment or not can_access_conversation(request, message.conversation):
        raise Http404
    if message.is_internal and not is_staff_user(request.user):
        raise Http404
    inline = message.attachment_type in _INLINE_TYPES and not request.GET.get("download")
    response = FileResponse(
        message.attachment.open("rb"),
        as_attachment=not inline,
        filename=message.attachment_name,
        content_type=message.attachment_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Cache-Control"] = "private, max-age=3600"
    return response


@csrf_exempt
@require_GET
def events_view(request: HttpRequest, conversation_id):
    try:
        conversation = get_conversation_for_request(request, conversation_id)
    except PermissionDenied:
        raise Http404
    if not can_access_conversation(request, conversation):
        raise Http404
    return streaming_response(str(conversation.pk), staff=False, request=request)
