import pytest

from supchat import permissions as p
from supchat.models import Conversation


def test_guest_token_roundtrip():
    assert p.unsign_guest_token(p.sign_guest_id("abc")) == "abc"


def test_guest_token_tampered_or_empty():
    assert p.unsign_guest_token(None) is None
    assert p.unsign_guest_token("garbage") is None
    assert p.unsign_guest_token(p.sign_guest_id("abc") + "x") is None


def test_guest_token_too_long():
    assert p.unsign_guest_token(p.sign_guest_id("a" * 65)) is None


def test_guest_token_expired(settings):
    settings.SUPCHAT = {"GUEST_COOKIE_AGE": -1}
    assert p.unsign_guest_token(p.sign_guest_id("abc")) is None


@pytest.mark.django_db
def test_access_matrix(mkreq, user, other_user, staff, operator):
    conv = Conversation.objects.create(user=user)
    assert p.can_access_conversation(mkreq(user), conv)
    assert not p.can_access_conversation(mkreq(other_user), conv)
    assert p.can_access_conversation(mkreq(staff), conv)
    assert not p.can_access_conversation(mkreq(), conv)


@pytest.mark.django_db
def test_guest_access_by_cookie(mkreq):
    conv = Conversation.objects.create(guest_id="g1")
    ok = mkreq(cookies={"supchat_guest": p.sign_guest_id("g1")})
    bad = mkreq(cookies={"supchat_guest": p.sign_guest_id("g2")})
    assert p.can_access_conversation(ok, conv)
    assert not p.can_access_conversation(bad, conv)


@pytest.mark.django_db
def test_cannot_send_to_closed(mkreq, user):
    conv = Conversation.objects.create(user=user, status="closed")
    assert not p.can_send_message(mkreq(user), conv)


@pytest.mark.django_db
def test_assign_permission(mkreq, user, staff, operator):
    conv = Conversation.objects.create(user=user)
    assert not p.can_assign_operator(mkreq(user), conv)
    assert not p.can_assign_operator(mkreq(), conv)
    assert p.can_assign_operator(mkreq(staff), conv)


@pytest.mark.django_db
def test_operator_helpers(user, staff, operator):
    assert p.is_operator_user(staff)
    assert not p.is_operator_user(user)
    assert p.get_operator_for_user(staff) == operator
    assert p.get_operator_for_user(user) is None
