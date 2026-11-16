import uuid

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from supchat import services as s
from supchat.models import Conversation, Message
from supchat.permissions import sign_guest_id
from supchat.services import RateLimitExceeded
from supchat.signals import conversation_closed, message_created, messages_read
from supchat.sse import sse_manager

pytestmark = pytest.mark.django_db


def test_get_or_create_for_user(mkreq, user):
    c1, gid = s.get_or_create_conversation(mkreq(user))
    c2, _ = s.get_or_create_conversation(mkreq(user))
    assert gid is None and c1 == c2 and c1.user == user


def test_new_conversation_after_close(mkreq, user):
    c1, _ = s.get_or_create_conversation(mkreq(user))
    c1.status = "closed"
    c1.save()
    c2, _ = s.get_or_create_conversation(mkreq(user))
    assert c1 != c2


def test_guest_gets_new_id_then_reuses(mkreq):
    c1, gid = s.get_or_create_conversation(mkreq())
    assert gid and c1.guest_id == gid
    c2, _ = s.get_or_create_conversation(mkreq(cookies={"supchat_guest": sign_guest_id(gid)}))
    assert c1 == c2


def test_guest_disabled(mkreq, settings):
    settings.SUPCHAT = {"ALLOW_GUEST": False}
    with pytest.raises(PermissionDenied):
        s.get_or_create_conversation(mkreq())


def test_send_message_sender_types(mkreq, user, staff, operator):
    conv = Conversation.objects.create(user=user)
    assert s.send_message(mkreq(user), conv, "hi").sender_type == "user"
    assert s.send_message(mkreq(staff), conv, "hi").sender_type == "operator"
    gconv = Conversation.objects.create(guest_id="g")
    req = mkreq(cookies={"supchat_guest": sign_guest_id("g")})
    assert s.send_message(req, gconv, "hi").sender_type == "guest"


def test_send_message_updates_conversation_and_fires_signal(mkreq, user):
    conv = Conversation.objects.create(user=user)
    seen = []
    message_created.connect(lambda **kw: seen.append(kw["message"]), weak=False, dispatch_uid="t1")
    try:
        m = s.send_message(mkreq(user), conv, "<i>hello</i>")
    finally:
        message_created.disconnect(dispatch_uid="t1")
    assert m.text == "hello" and seen == [m]
    conv.refresh_from_db()
    assert conv.last_message_at is not None


def test_send_message_denied(mkreq, user, other_user):
    conv = Conversation.objects.create(user=user)
    with pytest.raises(PermissionDenied):
        s.send_message(mkreq(other_user), conv, "hi")
    with pytest.raises(PermissionDenied):
        s.send_message(mkreq(), conv, "hi")


def test_send_message_invalid_text(mkreq, user):
    conv = Conversation.objects.create(user=user)
    with pytest.raises(ValidationError):
        s.send_message(mkreq(user), conv, "   ")
    assert Message.objects.count() == 0


def test_send_broadcasts(mkreq, user):
    conv = Conversation.objects.create(user=user)
    sub = sse_manager.subscribe(str(conv.pk))
    s.send_message(mkreq(user), conv, "yo")
    payload = sub.queue.get_nowait()
    assert payload["event"] == "message.created"
    assert payload["data"]["text"] == "yo"


def test_rate_limit_default(mkreq, user, settings):
    settings.SUPCHAT = {"RATE_LIMIT": {"MESSAGES": 2, "WINDOW": 60}}
    conv = Conversation.objects.create(user=user)
    req = mkreq(user)
    s.send_message(req, conv, "1")
    s.send_message(req, conv, "2")
    with pytest.raises(RateLimitExceeded):
        s.send_message(req, conv, "3")


def test_rate_limit_zero_disables(mkreq, user, settings):
    settings.SUPCHAT = {"RATE_LIMIT": {"MESSAGES": 0, "WINDOW": 60}}
    conv = Conversation.objects.create(user=user)
    for i in range(5):
        s.send_message(mkreq(user), conv, str(i))


def test_rate_limit_per_ip(mkreq, settings):
    settings.SUPCHAT = {"RATE_LIMIT": {"MESSAGES": 1, "WINDOW": 60}}
    a = mkreq(REMOTE_ADDR="1.1.1.1")
    b = mkreq(REMOTE_ADDR="2.2.2.2")
    s.check_rate_limit(a)
    s.check_rate_limit(b)
    with pytest.raises(RateLimitExceeded):
        s.check_rate_limit(a)


def test_rate_limit_callback(mkreq, user, settings):
    calls = []

    def cb(request, action):
        calls.append(action)
        return False

    settings.SUPCHAT = {"RATE_LIMIT_CALLBACK": cb}
    with pytest.raises(RateLimitExceeded):
        s.check_rate_limit(mkreq(user), "message")
    assert calls == ["message"]


def test_close_conversation(mkreq, user):
    conv = Conversation.objects.create(user=user)
    seen = []
    conversation_closed.connect(lambda **kw: seen.append(1), weak=False, dispatch_uid="t2")
    try:
        s.close_conversation(mkreq(user), conv)
        s.close_conversation(mkreq(user), conv)  # idempotent
    finally:
        conversation_closed.disconnect(dispatch_uid="t2")
    conv.refresh_from_db()
    assert conv.status == "closed" and len(seen) == 1


def test_close_denied(mkreq, user, other_user):
    conv = Conversation.objects.create(user=user)
    with pytest.raises(PermissionDenied):
        s.close_conversation(mkreq(other_user), conv)


def test_assign_operator(mkreq, user, staff, operator, operator2):
    conv = Conversation.objects.create(user=user)
    s.assign_operator(mkreq(staff), conv)
    assert conv.assigned_operator == operator
    s.assign_operator(mkreq(staff), conv, operator=operator2)
    assert conv.assigned_operator == operator2


def test_assign_denied_for_non_operator(mkreq, user):
    conv = Conversation.objects.create(user=user)
    with pytest.raises(PermissionDenied):
        s.assign_operator(mkreq(user), conv)


def test_assign_without_operator_profile(mkreq, user, User):
    conv = Conversation.objects.create(user=user)
    staff_no_op = User.objects.create_user("x", is_staff=True)
    with pytest.raises(ValidationError):
        s.assign_operator(mkreq(staff_no_op), conv)


def test_mark_read(mkreq, user):
    conv = Conversation.objects.create(user=user)
    m1 = Message.objects.create(conversation=conv, sender_type="operator", text="a")
    m2 = Message.objects.create(conversation=conv, sender_type="operator", text="b")
    seen = []
    messages_read.connect(lambda **kw: seen.append(kw["message_ids"]), weak=False, dispatch_uid="t3")
    try:
        assert s.mark_messages_read(mkreq(user), conv, [m1.id]) == 1
        assert s.mark_messages_read(mkreq(user), conv) == 1
        assert s.mark_messages_read(mkreq(user), conv) == 0
    finally:
        messages_read.disconnect(dispatch_uid="t3")
    assert seen == [[m1.id], [m2.id]]


def test_mark_read_denied(mkreq, user, other_user):
    conv = Conversation.objects.create(user=user)
    with pytest.raises(PermissionDenied):
        s.mark_messages_read(mkreq(other_user), conv)


def test_get_conversation_for_request(mkreq, user, other_user):
    conv = Conversation.objects.create(user=user)
    assert s.get_conversation_for_request(mkreq(user), conv.pk) == conv
    with pytest.raises(PermissionDenied):
        s.get_conversation_for_request(mkreq(other_user), conv.pk)
    with pytest.raises(PermissionDenied):
        s.get_conversation_for_request(mkreq(user), uuid.uuid4())


def test_operator_online_offline_broadcast(operator, user):
    conv = Conversation.objects.create(user=user, assigned_operator=operator)
    sub = sse_manager.subscribe(str(conv.pk))
    s.set_operator_online(operator)
    assert sub.queue.get_nowait()["event"] == "operator.online"
    s.set_operator_offline(operator)
    assert sub.queue.get_nowait()["event"] == "operator.offline"


def test_serialize(user):
    conv = Conversation.objects.create(user=user)
    m = Message.objects.create(conversation=conv, sender_type="user", sender_user=user, text="x")
    assert s.serialize_message(m)["sender_user"] == "alice"
    g = Message.objects.create(conversation=conv, sender_type="guest", text="y")
    assert s.serialize_message(g)["sender_user"] == "Guest"
    assert s.serialize_conversation(conv)["status"] == "open"
