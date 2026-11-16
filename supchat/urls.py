from django.urls import path

from . import operator_views as op
from . import views

app_name = "supchat"

urlpatterns = [
    # --- visitor API (also the mobile / custom-client API) ---
    path("config/", views.config_view, name="config"),
    path("start/", views.start_conversation_view, name="start"),
    path("conversations/<uuid:conversation_id>/messages/", views.messages_view, name="messages"),
    path("conversations/<uuid:conversation_id>/read/", views.mark_read_view, name="mark_read"),
    path("conversations/<uuid:conversation_id>/close/", views.close_conversation_view, name="close"),
    path("conversations/<uuid:conversation_id>/events/", views.events_view, name="events"),
    path("conversations/<uuid:conversation_id>/react/", views.react_view, name="react"),
    path("conversations/<uuid:conversation_id>/rate/", views.rate_view, name="rate"),
    path("conversations/<uuid:conversation_id>/profile/", views.profile_view, name="profile"),
    path("conversations/<uuid:conversation_id>/typing/", views.typing_view, name="visitor_typing"),
    path("conversations/<uuid:conversation_id>/transcript/", views.transcript_download_view, name="transcript"),
    path("conversations/<uuid:conversation_id>/transcript/email/", views.transcript_email_view, name="transcript_email"),
    path("attachments/<int:message_id>/", views.attachment_view, name="attachment"),
    # --- operator panel ---
    path("operator/", op.dashboard_view, name="operator_dashboard"),
    # client-side routes of the single-page panel (deep links / reloads land on the same shell)
    path("operator/c/<uuid:conversation_id>/", op.dashboard_view, name="operator_chat"),
    path("operator/analytics/", op.dashboard_view, name="operator_analytics_page"),
    path("operator/settings/", op.dashboard_view, name="operator_settings"),
    path("operator/settings/<slug:tab>/", op.dashboard_view, name="operator_settings_tab"),
    path("operator/partials/dashboard/", op.dashboard_partial, name="operator_dashboard_partial"),
    path("operator/api/bootstrap/", op.bootstrap_api, name="operator_bootstrap"),
    path("operator/api/heartbeat/", op.heartbeat_api, name="operator_heartbeat"),
    path("operator/api/analytics/", op.analytics_api, name="operator_analytics"),
    path("operator/api/stream/", op.operator_events, name="operator_stream"),
    path("operator/api/tags/", op.tag_create, name="operator_tag_create"),
    path("operator/api/tags/<int:tag_id>/delete/", op.tag_delete, name="operator_tag_delete"),
    path("operator/api/canned/", op.canned_create, name="operator_canned_create"),
    path("operator/api/canned/<int:canned_id>/delete/", op.canned_delete, name="operator_canned_delete"),
    path("operator/api/blocked/<int:blocked_id>/delete/", op.unblock, name="operator_unblock"),
    path("operator/api/webhooks/<int:webhook_id>/test/", op.webhook_test, name="operator_webhook_test"),
    path("operator/conversations/", op.conversation_list_api, name="operator_conversation_list"),
    path("operator/conversations/<uuid:conversation_id>/", op.conversation_detail_view, name="operator_conversation_detail"),
    path("operator/conversations/<uuid:conversation_id>/send/", op.operator_send_message, name="operator_send_message"),
    path("operator/conversations/<uuid:conversation_id>/close/", op.operator_close_conversation, name="operator_close"),
    path("operator/conversations/<uuid:conversation_id>/reopen/", op.operator_reopen_conversation, name="operator_reopen"),
    path("operator/conversations/<uuid:conversation_id>/delete/", op.operator_delete_conversation, name="operator_delete"),
    path("operator/conversations/<uuid:conversation_id>/assign/", op.operator_assign, name="operator_assign"),
    path("operator/conversations/<uuid:conversation_id>/update/", op.operator_update, name="operator_update"),
    path("operator/conversations/<uuid:conversation_id>/tags/", op.operator_tags, name="operator_tags"),
    path("operator/conversations/<uuid:conversation_id>/block/", op.operator_block, name="operator_block"),
    path("operator/conversations/<uuid:conversation_id>/react/", op.operator_react, name="operator_react"),
    path("operator/conversations/<uuid:conversation_id>/events/", op.operator_events, name="operator_events"),
    path("operator/conversations/<uuid:conversation_id>/typing/", op.typing_view, name="typing_view"),
    path("operator/conversations/<uuid:conversation_id>/transcript/", op.operator_transcript, name="operator_transcript"),
    path("operator/conversations/<uuid:conversation_id>/transcript/email/", op.operator_transcript_email, name="operator_transcript_email"),
]
