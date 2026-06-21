from django.urls import path

from . import views

app_name = "supchat"

urlpatterns = [
    path("start/", views.start_conversation_view, name="start"),
    path("conversations/<uuid:conversation_id>/messages/", views.messages_view, name="messages"),
    path("conversations/<uuid:conversation_id>/read/", views.mark_read_view, name="mark_read"),
    path("conversations/<uuid:conversation_id>/close/", views.close_conversation_view, name="close"),
    path("conversations/<uuid:conversation_id>/events/", views.events_view, name="events"),
]
