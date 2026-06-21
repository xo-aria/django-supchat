import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from supchat.models import Conversation, Operator
from supchat.permissions import can_access_conversation, sign_guest_id

pytestmark = pytest.mark.django_db


def anon_request(cookie=None):
    request = RequestFactory().get("/", HTTP_COOKIE=cookie or "")
    request.user = type("Anonymous", (), {"is_authenticated": False})()
    return request


def test_guest_permission_requires_valid_signed_cookie():
    conversation = Conversation.objects.create(guest_id="abc")
    assert can_access_conversation(anon_request("supchat_guest=" + sign_guest_id("abc")), conversation)
    assert not can_access_conversation(anon_request("supchat_guest=tampered"), conversation)


def test_operator_can_access_conversation():
    user = get_user_model().objects.create_user("operator")
    Operator.objects.create(user=user)
    request = RequestFactory().get("/")
    request.user = user
    conversation = Conversation.objects.create(guest_id="abc")
    assert can_access_conversation(request, conversation)
