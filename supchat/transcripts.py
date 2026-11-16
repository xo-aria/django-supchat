from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail

from .conf import supchat_settings
from .models import Conversation, Message


def build_transcript(conversation: Conversation, include_internal: bool = False) -> str:
    qs = conversation.messages.select_related("sender_user").order_by("created_at", "id")
    if not include_internal:
        qs = qs.filter(is_internal=False)
    lines = [
        f"Conversation {conversation.pk}",
        f"Participant: {conversation.display_name}",
        f"Status: {conversation.status}",
        f"Started: {conversation.created_at:%Y-%m-%d %H:%M}",
        "-" * 40,
    ]
    for m in qs:
        who = {
            Message.SenderType.OPERATOR: "Support",
            Message.SenderType.BOT: "Assistant",
            Message.SenderType.SYSTEM: "System",
        }.get(m.sender_type, conversation.display_name)
        if m.is_internal:
            who += " (internal note)"
        body = m.text or ""
        if m.attachment_name:
            body = (body + f" [file: {m.attachment_name}]").strip()
        lines.append(f"[{m.created_at:%Y-%m-%d %H:%M}] {who}: {body}")
    return "\n".join(lines) + "\n"


def send_transcript_email(conversation: Conversation, to_email: str) -> int:
    sender = supchat_settings.get("TRANSCRIPT_EMAIL_FROM") or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    return send_mail(
        subject=f"{supchat_settings.get('TITLE')} - chat transcript",
        message=build_transcript(conversation),
        from_email=sender,
        recipient_list=[to_email],
        fail_silently=False,
    )
