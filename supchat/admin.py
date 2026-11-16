from __future__ import annotations

from django.contrib import admin

from .models import BlockedVisitor, CannedResponse, Conversation, Message, Operator, Reaction, Tag, WebhookEndpoint


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    fields = ("sender_type", "sender_user", "text", "is_internal", "attachment_name", "is_read", "created_at")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "participant", "status", "priority", "assigned_operator", "rating", "last_message_at", "created_at")
    list_filter = ("status", "priority", "ai_enabled", "assigned_operator", "tags", "created_at")
    search_fields = ("id", "guest_id", "visitor_name", "visitor_email", "subject", "user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at", "last_message_at", "ip_hash", "user_agent", "first_response_at", "closed_at")
    autocomplete_fields = ("user", "assigned_operator")
    filter_horizontal = ("tags",)
    inlines = (MessageInline,)
    list_select_related = ("user", "assigned_operator__user")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "assigned_operator__user")

    @admin.display(description="Participant")
    def participant(self, obj: Conversation):
        return obj.display_name


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender_type", "sender_user", "is_internal", "is_read", "created_at")
    list_filter = ("sender_type", "is_internal", "is_read", "created_at")
    search_fields = ("conversation__id", "sender_user__username", "sender_user__email", "text")
    readonly_fields = ("conversation", "sender_type", "sender_user", "text", "is_read", "is_internal", "reply_to",
                       "attachment", "attachment_name", "attachment_type", "attachment_size", "created_at")
    list_select_related = ("conversation", "sender_user")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("user", "is_online", "last_seen")
    list_filter = ("is_online", "last_seen")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color")
    search_fields = ("name",)


@admin.register(CannedResponse)
class CannedResponseAdmin(admin.ModelAdmin):
    list_display = ("shortcut", "title")
    search_fields = ("shortcut", "title", "text")


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active", "events", "last_status", "last_at")
    list_filter = ("kind", "is_active")
    readonly_fields = ("last_status", "last_error", "last_at")


@admin.register(BlockedVisitor)
class BlockedVisitorAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reason", "created_by", "created_at")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("message", "emoji", "actor", "created_at")
