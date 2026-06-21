from __future__ import annotations
import uuid
import django
from django.conf import settings
from django.db import models
from django.utils import timezone


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


class Message(models.Model):
    class SenderType(models.TextChoices):
        USER = "user", "User"
        GUEST = "guest", "Guest"
        OPERATOR = "operator", "Operator"
        SYSTEM = "system", "System"

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
    text = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "is_read"]),
            models.Index(fields=["sender_type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Message {self.pk} in {self.conversation_id}"
