import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, override_settings

from supchat.models import Conversation, Message, Operator
from supchat.permissions import sign_guest_id
from supchat.services import close_conversation, get_or_create_conversation, send_message

pytestmark = pytest.mark.django_db


def request_with_user(user):
    request = RequestFactory().post("/")
    request.user = user
    return request


def test_authenticated_conversation_and_message_sanitized():
    user = get_user_model().objects.create_user("bob")
    request = request_with_user(user)
    conversation, guest_id = get_or_create_conversation(request)
    assert guest_id is None
    message = send_message(request, conversation, " <b>Hello</b>\x00 ")
    assert message.text == "Hello"
    assert message.sender_type == Message.SenderType.USER


def test_guest_conversation_uses_signed_cookie():
    request = RequestFactory().post("/", HTTP_COOKIE="supchat_guest=" + sign_guest_id("guest123"))
    request.user = type("Anonymous", (), {"is_authenticated": False})()
    conversation, guest_id = get_or_create_conversation(request)
    assert conversation.guest_id == "guest123"
    assert guest_id == "guest123"


def test_max_length_enforced():
    user = get_user_model().objects.create_user("max")
    conversation = Conversation.objects.create(user=user)
    with pytest.raises(ValidationError):
        send_message(request_with_user(user), conversation, "x" * 101)


def test_closed_conversation_rejects_messages():
    user = get_user_model().objects.create_user("closed")
    conversation = Conversation.objects.create(user=user)
    request = request_with_user(user)
    close_conversation(request, conversation)
    conversation.refresh_from_db()
    with pytest.raises(PermissionDenied):
        send_message(request, conversation, "hello")


def test_operator_message_sender_type():
    user = get_user_model().objects.create_user("op")
    Operator.objects.create(user=user)
    conversation = Conversation.objects.create(guest_id="guest")
    message = send_message(request_with_user(user), conversation, "Hi")
    assert message.sender_type == Message.SenderType.OPERATOR
