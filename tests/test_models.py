import pytest
from django.db import IntegrityError, transaction

from supchat.models import Conversation, Message


@pytest.mark.django_db
def test_conversation_requires_participant():
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create()


@pytest.mark.django_db
def test_conversation_defaults(user):
    c = Conversation.objects.create(user=user)
    assert c.status == Conversation.Status.OPEN
    assert "open" in str(c)


@pytest.mark.django_db
def test_message_ordering_and_str(user):
    c = Conversation.objects.create(user=user)
    m1 = Message.objects.create(conversation=c, sender_type="user", text="1")
    m2 = Message.objects.create(conversation=c, sender_type="user", text="2")
    assert list(c.messages.all()) == [m1, m2]
    assert str(m1)


@pytest.mark.django_db
def test_operator_online_offline(operator):
    operator.mark_online()
    operator.refresh_from_db()
    assert operator.is_online and operator.last_seen
    operator.mark_offline()
    operator.refresh_from_db()
    assert not operator.is_online
    assert str(operator) == "staff"


@pytest.mark.django_db
def test_message_cascade_on_conversation_delete(user):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="x")
    c.delete()
    assert Message.objects.count() == 0
