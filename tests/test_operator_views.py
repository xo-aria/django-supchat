import uuid

import pytest

from supchat.models import Conversation, Message, Operator
from supchat.sse import sse_manager

pytestmark = pytest.mark.django_db


@pytest.fixture
def conv(user):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", sender_user=user, text="help me")
    return c


def test_dashboard_requires_staff(guest_client, user_client):
    assert guest_client.get("/supchat/operator/").status_code == 302
    assert user_client.get("/supchat/operator/").status_code == 302


def test_dashboard_ok_and_marks_online(staff_client, operator):
    assert staff_client.get("/supchat/operator/").status_code == 200
    operator.refresh_from_db()
    assert operator.is_online


def test_dashboard_partial(staff_client, conv):
    assert staff_client.get("/supchat/operator/partials/dashboard/").status_code == 200


def test_staff_without_operator_auto_created(User, client):
    u = User.objects.create_user("s2", is_staff=True)
    client.force_login(u)
    assert client.get("/supchat/operator/").status_code == 200
    assert Operator.objects.filter(user=u).exists()


def test_conversation_list(staff_client, conv):
    data = staff_client.get("/supchat/operator/conversations/").json()
    assert data["conversations"][0]["id"] == str(conv.pk)
    assert data["conversations"][0]["unread_count"] == 1
    assert data["conversations"][0]["participant"] == "alice"


def test_list_preview_truncated(staff_client, user):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="x" * 200)
    prev = staff_client.get("/supchat/operator/conversations/").json()["conversations"][0]["last_message_preview"]
    assert prev.endswith("...") and len(prev) == 83


def test_detail_marks_read(staff_client, conv):
    data = staff_client.get(f"/supchat/operator/conversations/{conv.pk}/").json()
    assert data["conversation"]["participant"] == "alice"
    assert len(data["messages"]) == 1
    assert not Message.objects.filter(is_read=False).exists()


def test_detail_404(staff_client):
    assert staff_client.get(f"/supchat/operator/conversations/{uuid.uuid4()}/").status_code == 404


def test_operator_send(staff_client, pj, conv):
    r = pj(staff_client, f"/supchat/operator/conversations/{conv.pk}/send/", {"text": "hi alice"})
    assert r.status_code == 201
    assert r.json()["message"]["sender_type"] == "operator"


def test_operator_send_errors(staff_client, pj, conv):
    url = f"/supchat/operator/conversations/{conv.pk}/send/"
    assert pj(staff_client, url, {"text": ""}).status_code == 400
    assert staff_client.post(url, data="{", content_type="application/json").status_code == 400
    assert staff_client.get(url).status_code == 405


def test_operator_send_closed_forbidden(staff_client, pj, conv):
    conv.status = "closed"
    conv.save()
    r = pj(staff_client, f"/supchat/operator/conversations/{conv.pk}/send/", {"text": "x"})
    assert r.status_code == 403


def test_operator_close(staff_client, conv):
    r = staff_client.post(f"/supchat/operator/conversations/{conv.pk}/close/")
    assert r.json() == {"ok": True, "status": "closed"}


def test_operator_delete(staff_client, conv):
    assert staff_client.post(f"/supchat/operator/conversations/{conv.pk}/delete/").json()["deleted"]
    assert not Conversation.objects.exists() and not Message.objects.exists()


def test_operator_assign(staff_client, pj, conv, operator, operator2):
    url = f"/supchat/operator/conversations/{conv.pk}/assign/"
    assert pj(staff_client, url, {"operator_id": operator2.pk}).status_code == 200
    conv.refresh_from_db()
    assert conv.assigned_operator == operator2
    assert pj(staff_client, url, {}).status_code == 200  # self-assign
    conv.refresh_from_db()
    assert conv.assigned_operator == operator
    assert pj(staff_client, url, {"operator_id": 9999}).status_code == 404


def test_mutations_forbidden_for_non_staff(user_client, conv):
    for action in ("close", "delete"):
        r = user_client.post(f"/supchat/operator/conversations/{conv.pk}/{action}/")
        assert r.status_code == 302
    assert Conversation.objects.filter(pk=conv.pk).exists()


def test_operator_events_stream(staff_client, conv):
    r = staff_client.get(f"/supchat/operator/conversations/{conv.pk}/events/")
    assert r["Content-Type"] == "text/event-stream"
    r.close()


def test_typing_broadcast(staff_client, pj, conv):
    sub = sse_manager.subscribe(str(conv.pk))
    url = f"/supchat/operator/conversations/{conv.pk}/typing/"
    assert pj(staff_client, url, {"is_typing": True}).status_code == 200
    ev = sub.queue.get_nowait()
    assert ev["event"] == "typing.start" and ev["data"]["sender_type"] == "operator"
    pj(staff_client, url, {"is_typing": False})
    assert sub.queue.get_nowait()["event"] == "typing.stop"


def test_chart_data(conv):
    from supchat.operator_views import _get_chart_data

    labels, values = _get_chart_data(7)
    assert len(labels) == len(values) == 7
    assert sum(values) == 1
