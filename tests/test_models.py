import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from supchat.models import Conversation, Message, Operator

pytestmark = pytest.mark.django_db


def test_models_create_with_indexes():
    user = get_user_model().objects.create_user("alice")
    operator = Operator.objects.create(user=user, is_online=True)
    conversation = Conversation.objects.create(user=user, assigned_operator=operator)
    message = Message.objects.create(conversation=conversation, sender_type=Message.SenderType.USER, sender_user=user, text="Hello")
    assert str(conversation.id) in str(conversation)
    assert message.conversation_id == conversation.id
    assert operator.is_online is True


def test_conversation_requires_participant():
    with pytest.raises(IntegrityError):
        Conversation.objects.create()
