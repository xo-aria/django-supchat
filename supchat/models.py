from __future__ import annotations
import os
import uuid
import django
from django.conf import settings
from django.db import models
from django.utils import timezone


def attachment_upload_path(instance, filename: str) -> str:
    """Random stored name; the visitor-facing name lives in ``attachment_name``."""
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"supchat/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class Operator(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supchat_operator",
    )
    is_online = models.BooleanField(default=False, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["user__username"]
        indexes = [models.Index(fields=["is_online", "last_seen"]) ]

    def __str__(self) -> str:
        return str(self.user)

    def mark_online(self) -> None:
        self.is_online = True
        self.last_seen = timezone.now()
        self.save(update_fields=["is_online", "last_seen"])

    def mark_offline(self) -> None:
        self.is_online = False
        self.last_seen = timezone.now()
        self.save(update_fields=["is_online", "last_seen"])


class Conversation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supchat_conversations",
    )
    guest_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_operator = models.ForeignKey(
        Operator,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    subject = models.CharField(max_length=120, blank=True, default="")
    visitor_name = models.CharField(max_length=80, blank=True, default="")
    visitor_email = models.EmailField(blank=True, default="")
    locale = models.CharField(max_length=8, blank=True, default="")
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    tags = models.ManyToManyField("Tag", blank=True, related_name="conversations")
    ai_enabled = models.BooleanField(default=True, help_text="AI auto-replies are active until an operator takes over.")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_comment = models.CharField(max_length=500, blank=True, default="")
    ip_hash = models.CharField(max_length=32, blank=True, default="", db_index=True)
    user_agent = models.CharField(max_length=200, blank=True, default="")
    first_response_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "last_message_at"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["guest_id", "status"]),
            models.Index(fields=["assigned_operator", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                **({"condition": models.Q(user__isnull=False) | models.Q(guest_id__isnull=False)} if django.VERSION >= (5, 1) else {"check": models.Q(user__isnull=False) | models.Q(guest_id__isnull=False)}),
                name="supchat_conversation_has_participant",
            ),
        ]

    def __str__(self) -> str:
        return f"Conversation {self.pk} ({self.status})"

    @property
    def display_name(self) -> str:
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        if self.visitor_name:
            return self.visitor_name
        return f"Guest {self.guest_id[:6]}" if self.guest_id else "Guest"


class Message(models.Model):
    class SenderType(models.TextChoices):
        USER = "user", "User"
        GUEST = "guest", "Guest"
        OPERATOR = "operator", "Operator"
        SYSTEM = "system", "System"
        BOT = "bot", "Bot"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender_type = models.CharField(max_length=16, choices=SenderType.choices, db_index=True)
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supchat_messages",
    )
    text = models.TextField(blank=True, default="")
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_internal = models.BooleanField(default=False, db_index=True, help_text="Private operator note, never shown to the visitor.")
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    attachment = models.FileField(upload_to=attachment_upload_path, null=True, blank=True, max_length=200)
    attachment_name = models.CharField(max_length=200, blank=True, default="")
    attachment_type = models.CharField(max_length=100, blank=True, default="")
    attachment_size = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "is_read"]),
            models.Index(fields=["sender_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Message {self.pk} in {self.conversation_id}"



class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=16)
    actor = models.CharField(max_length=80, help_text="u:<id>, g:<guest>, or o:<operator id>.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "emoji", "actor"], name="supchat_unique_reaction")]

    def __str__(self) -> str:
        return f"{self.emoji} on {self.message_id}"


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)
    color = models.CharField(max_length=7, default="#3390ec")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CannedResponse(models.Model):
    shortcut = models.SlugField(max_length=40, unique=True, help_text="Type /shortcut in the composer.")
    title = models.CharField(max_length=80)
    text = models.TextField(max_length=2000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["shortcut"]

    def __str__(self) -> str:
        return f"/{self.shortcut}"


class WebhookEndpoint(models.Model):
    class Kind(models.TextChoices):
        GENERIC = "generic", "Generic JSON (signed)"
        SLACK = "slack", "Slack"
        DISCORD = "discord", "Discord"

    name = models.CharField(max_length=80)
    url = models.URLField(max_length=500)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.GENERIC)
    secret = models.CharField(max_length=128, blank=True, default="", help_text="HMAC-SHA256 key for generic webhooks.")
    events = models.CharField(max_length=200, default="*", help_text="Comma separated event names or *.")
    is_active = models.BooleanField(default=True)
    last_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")
    last_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    def wants(self, event: str) -> bool:
        wanted = [e.strip() for e in self.events.split(",") if e.strip()]
        return "*" in wanted or event in wanted


class BlockedVisitor(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    guest_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ip_hash = models.CharField(max_length=32, blank=True, default="", db_index=True)
    reason = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user) if self.user_id else (self.guest_id or self.ip_hash or "blocked")
