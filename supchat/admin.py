from __future__ import annotations

from django.contrib import admin

from .models import Conversation, Message, Operator


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    fields = ("sender_type", "sender_user", "text", "is_read", "created_at")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "participant", "status", "assigned_operator", "last_message_at", "created_at")
    list_filter = ("status", "assigned_operator", "created_at", "last_message_at")
    search_fields = ("id", "guest_id", "user__username", "user__email", "assigned_operator__user__username")
    readonly_fields = ("id", "created_at", "updated_at", "last_message_at")
    autocomplete_fields = ("user", "assigned_operator")
    inlines = (MessageInline,)
    list_select_related = ("user", "assigned_operator__user")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "assigned_operator__user")

    @admin.display(description="Participant")
    def participant(self, obj: Conversation):
        return obj.user or f"Guest {obj.guest_id[:8] if obj.guest_id else '-'}"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender_type", "sender_user", "is_read", "created_at")
    list_filter = ("sender_type", "is_read", "created_at")
    search_fields = ("conversation__id", "sender_user__username", "sender_user__email", "text")
    readonly_fields = ("conversation", "sender_type", "sender_user", "text", "is_read", "created_at")
    list_select_related = ("conversation", "sender_user")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("supchat.view_message")


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("user", "is_online", "last_seen")
    list_filter = ("is_online", "last_seen")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
