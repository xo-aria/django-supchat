from django.urls import path

from . import views
from . import operator_views

app_name = "supchat"

urlpatterns = [
    path("start/", views.start_conversation_view, name="start"),
    path("conversations/<uuid:conversation_id>/messages/", views.messages_view, name="messages"),
    path("conversations/<uuid:conversation_id>/read/", views.mark_read_view, name="mark_read"),
    path("conversations/<uuid:conversation_id>/close/", views.close_conversation_view, name="close"),
    path("conversations/<uuid:conversation_id>/events/", views.events_view, name="events"),
    path('conversations/<uuid:conversation_id>/typing/', operator_views.typing_view, name='supchat_typing'),

    path("operator/", operator_views.dashboard_view, name="operator_dashboard"),
    path("operator/partials/dashboard/", operator_views.dashboard_partial, name="operator_dashboard_partial"),
    path("operator/conversations/", operator_views.conversation_list_api, name="operator_conversation_list"),
    path("operator/conversations/<uuid:conversation_id>/", operator_views.conversation_detail_view, name="operator_conversation_detail"),
    path("operator/conversations/<uuid:conversation_id>/send/", operator_views.operator_send_message, name="operator_send_message"),
    path("operator/conversations/<uuid:conversation_id>/close/", operator_views.operator_close_conversation, name="operator_close"),
    path("operator/conversations/<uuid:conversation_id>/delete/", operator_views.operator_delete_conversation, name="operator_delete"),
    path("operator/conversations/<uuid:conversation_id>/assign/", operator_views.operator_assign, name="operator_assign"),
    path("operator/conversations/<uuid:conversation_id>/events/", operator_views.operator_events, name="operator_events"),
    path("operator/conversations/<uuid:conversation_id>/typing/", operator_views.typing_view, name="typing_view"),
]