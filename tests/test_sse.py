import itertools

import pytest
from django.test import RequestFactory

from supchat.models import Conversation
from supchat.permissions import sign_guest_id
from supchat.sse import event_stream, format_sse, sse_manager
from supchat.views import events_view

pytestmark = pytest.mark.django_db


def test_format_sse_is_valid():
    rendered = format_sse("message.created", {"text": "hello"}, event_id="1")
    assert "event: message.created" in rendered
    assert 'data: {"text":"hello"}' in rendered


def test_sse_authorization_rejects_bad_guest():
    from django.http import Http404

    conversation = Conversation.objects.create(guest_id="abc")
    request = RequestFactory().get("/")
    request.user = type("Anonymous", (), {"is_authenticated": False})()
    with pytest.raises(Http404):
        events_view(request, conversation.id)


def test_event_stream_receives_broadcast():
    conversation_id = "c1"
    stream = event_stream(conversation_id)
    assert next(stream).startswith("retry:")
    assert "connected" in next(stream)
    sse_manager.broadcast(conversation_id, "message.created", {"id": 1})
    assert "message.created" in next(stream)
    stream.close()
