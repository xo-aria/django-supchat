import uuid
from unittest import mock

import pytest
from django.core import mail

from supchat.models import BlockedVisitor, CannedResponse, Conversation, Message, Operator, Tag, WebhookEndpoint
from supchat.sse import STAFF_CHANNEL, sse_manager

pytestmark = pytest.mark.django_db
OP = "/supchat/operator/"


@pytest.fixture
def conv(user):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", sender_user=user, text="help me")
    return c


@pytest.fixture
def guest_conv():
    c = Conversation.objects.create(guest_id="g" * 32, visitor_name="Sara", visitor_email="sara@example.com", ip_hash="h" * 32)
    Message.objects.create(conversation=c, sender_type="guest", text="hi")
    return c


# ------------------------------------------------------------ access control
def test_dashboard_requires_staff(guest_client, user_client):
    assert guest_client.get(OP).status_code == 302
    assert user_client.get(OP).status_code == 302


def test_dashboard_ok_and_marks_online(staff_client, operator):
    r = staff_client.get(OP)
    assert r.status_code == 200 and b"operator.js" in r.content
    operator.refresh_from_db()
    assert operator.is_online


def test_legacy_partial_alias(staff_client):
    assert staff_client.get(OP + "partials/dashboard/").status_code == 200


def test_staff_without_operator_auto_created(User, client):
    u = User.objects.create_user("s2", is_staff=True)
    client.force_login(u)
    assert client.get(OP).status_code == 200
    assert Operator.objects.filter(user=u).exists()


@pytest.mark.parametrize("path", ["api/bootstrap/", "conversations/", "api/analytics/"])
def test_api_anonymous_401_and_user_403(guest_client, user_client, path):
    assert guest_client.get(OP + path).status_code == 401
    assert user_client.get(OP + path).status_code == 403


def test_mutations_forbidden_for_non_staff(user_client, conv):
    for action in ("close", "delete", "block", "reopen"):
        assert user_client.post(f"{OP}conversations/{conv.pk}/{action}/").status_code == 403
    assert Conversation.objects.filter(pk=conv.pk, status="open").exists()


def test_csrf_enforced_on_operator_api(staff, operator, conv):
    from django.test import Client

    c = Client(enforce_csrf_checks=True)
    c.force_login(staff)
    assert c.post(f"{OP}conversations/{conv.pk}/close/").status_code == 403


# ----------------------------------------------------------------- bootstrap
def test_bootstrap(staff_client, operator):
    Tag.objects.create(name="Bug", color="#ff0000")
    CannedResponse.objects.create(shortcut="hi", title="Hi", text="Hello!")
    d = staff_client.get(OP + "api/bootstrap/").json()
    assert d["me"]["id"] == operator.pk
    assert d["tags"][0]["name"] == "Bug" and d["canned"][0]["shortcut"] == "hi"
    assert "fa" in d["languages"] and d["webhooks"] == []  # webhooks are superuser-only


def test_bootstrap_superuser_sees_webhooks(User, client):
    su = User.objects.create_superuser("root", password="x")
    WebhookEndpoint.objects.create(name="Slack", url="https://hooks.example.com/x", kind="slack")
    client.force_login(su)
    assert client.get(OP + "api/bootstrap/").json()["webhooks"][0]["name"] == "Slack"


def test_heartbeat(staff_client, operator):
    assert staff_client.post(OP + "api/heartbeat/").json()["ok"]
    operator.refresh_from_db()
    assert operator.is_online and operator.last_seen


# ---------------------------------------------------------------------- list
def test_conversation_list(staff_client, conv):
    data = staff_client.get(OP + "conversations/").json()
    row = data["conversations"][0]
    assert row["id"] == str(conv.pk) and row["unread_count"] == 1 and row["participant"] == "alice"
    assert data["counts"]["open"] == 1 and data["counts"]["unassigned"] == 1


def test_list_hides_conversations_without_messages(staff_client, user):
    Conversation.objects.create(user=user)
    assert staff_client.get(OP + "conversations/").json()["conversations"] == []


def test_list_preview_truncated(staff_client, user):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="x" * 200)
    prev = staff_client.get(OP + "conversations/").json()["conversations"][0]["last_message_preview"]
    assert len(prev) == 80


def test_list_preview_ignores_internal_notes(staff_client, conv):
    Message.objects.create(conversation=conv, sender_type="operator", text="secret note", is_internal=True)
    assert staff_client.get(OP + "conversations/").json()["conversations"][0]["last_message_preview"] == "help me"


def test_list_filters(staff_client, operator, conv, guest_conv):
    conv.assigned_operator = operator
    conv.save()
    guest_conv.status = "closed"
    guest_conv.save()
    ids = lambda q: [c["id"] for c in staff_client.get(OP + "conversations/?" + q).json()["conversations"]]  # noqa: E731
    assert ids("status=open") == [str(conv.pk)]
    assert ids("status=closed") == [str(guest_conv.pk)]
    assert ids("assigned=me") == [str(conv.pk)]
    assert ids("assigned=unassigned&status=all") == [str(guest_conv.pk)]
    assert set(ids("status=all")) == {str(conv.pk), str(guest_conv.pk)}


def test_list_search_and_tag_filter(staff_client, conv, guest_conv):
    tag = Tag.objects.create(name="VIP")
    guest_conv.tags.add(tag)
    q = lambda s: [c["id"] for c in staff_client.get(OP + "conversations/?status=all&" + s).json()["conversations"]]  # noqa: E731
    assert q("q=sara") == [str(guest_conv.pk)]
    assert q("q=help") == [str(conv.pk)]
    assert q(f"tag={tag.pk}") == [str(guest_conv.pk)]


def test_list_pagination(staff_client, user):
    for i in range(3):
        c = Conversation.objects.create(user=user)
        Message.objects.create(conversation=c, sender_type="user", text=str(i))
    d = staff_client.get(OP + "conversations/?limit=2").json()
    assert len(d["conversations"]) == 2 and d["has_more"]
    d = staff_client.get(OP + "conversations/?limit=2&offset=2").json()
    assert len(d["conversations"]) == 1 and not d["has_more"]


# -------------------------------------------------------------------- detail
def test_detail_marks_visitor_messages_read(staff_client, conv):
    data = staff_client.get(f"{OP}conversations/{conv.pk}/").json()
    assert data["conversation"]["participant"] == "alice"
    assert len(data["messages"]) == 1
    assert not Message.objects.filter(is_read=False).exists()


def test_detail_includes_internal_notes(staff_client, conv):
    Message.objects.create(conversation=conv, sender_type="operator", text="note", is_internal=True)
    msgs = staff_client.get(f"{OP}conversations/{conv.pk}/").json()["messages"]
    assert [m["is_internal"] for m in msgs] == [False, True]


def test_detail_pagination(staff_client, user):
    c = Conversation.objects.create(user=user)
    Message.objects.bulk_create([Message(conversation=c, sender_type="user", text=str(i)) for i in range(105)])
    d = staff_client.get(f"{OP}conversations/{c.pk}/").json()
    assert len(d["messages"]) == 100 and d["has_more"] and d["messages"][-1]["text"] == "104"
    first = d["messages"][0]["id"]
    d2 = staff_client.get(f"{OP}conversations/{c.pk}/?before={first}").json()
    assert len(d2["messages"]) == 5 and not d2["has_more"]


def test_detail_404(staff_client):
    assert staff_client.get(f"{OP}conversations/{uuid.uuid4()}/").status_code == 404


# ---------------------------------------------------------------------- send
def test_operator_send(staff_client, pj, conv):
    r = pj(staff_client, f"{OP}conversations/{conv.pk}/send/", {"text": "hi alice"})
    assert r.status_code == 201 and r.json()["message"]["sender_type"] == "operator"
    conv.refresh_from_db()
    assert conv.first_response_at is not None and conv.ai_enabled is False


def test_operator_internal_note_not_broadcast_to_visitor(staff_client, pj, conv):
    visitor = sse_manager.subscribe(str(conv.pk))
    staff = sse_manager.subscribe(STAFF_CHANNEL, staff=True)
    r = pj(staff_client, f"{OP}conversations/{conv.pk}/send/", {"text": "they are VIP", "internal": True})
    assert r.json()["message"]["is_internal"] is True
    assert visitor.queue.empty()
    assert staff.queue.get_nowait()["event"] == "message.created"
    conv.refresh_from_db()
    assert conv.first_response_at is None  # notes are not responses


def test_operator_send_multipart_with_attachment(staff_client, conv, png):
    r = staff_client.post(f"{OP}conversations/{conv.pk}/send/", {"text": "", "file": png()})
    assert r.status_code == 201
    att = r.json()["message"]["attachment"]
    assert att["is_image"] and att["name"] == "pic.png"


def test_operator_send_reply(staff_client, pj, conv):
    first = conv.messages.first()
    r = pj(staff_client, f"{OP}conversations/{conv.pk}/send/", {"text": "answer", "reply_to": first.pk})
    assert r.json()["message"]["reply_to"]["id"] == first.pk


def test_operator_send_errors(staff_client, pj, conv):
    url = f"{OP}conversations/{conv.pk}/send/"
    assert pj(staff_client, url, {"text": ""}).status_code == 400
    assert staff_client.post(url, data="{", content_type="application/json").status_code == 400
    assert staff_client.get(url).status_code == 405
    assert pj(staff_client, f"{OP}conversations/{uuid.uuid4()}/send/", {"text": "x"}).status_code == 404


def test_operator_send_closed_forbidden(staff_client, pj, conv):
    conv.status = "closed"
    conv.save()
    assert pj(staff_client, f"{OP}conversations/{conv.pk}/send/", {"text": "x"}).status_code == 403


# ------------------------------------------------------------------- actions
def test_close_and_reopen(staff_client, conv):
    assert staff_client.post(f"{OP}conversations/{conv.pk}/close/").json() == {"ok": True, "status": "closed"}
    conv.refresh_from_db()
    assert conv.closed_at is not None
    assert staff_client.post(f"{OP}conversations/{conv.pk}/reopen/").json()["status"] == "open"
    conv.refresh_from_db()
    assert conv.closed_at is None


def test_delete_removes_files(staff_client, conv, png, settings):
    import os

    r = staff_client.post(f"{OP}conversations/{conv.pk}/send/", {"file": png()})
    path = Message.objects.get(pk=r.json()["message"]["id"]).attachment.path
    assert os.path.exists(path)
    assert staff_client.post(f"{OP}conversations/{conv.pk}/delete/").json()["deleted"]
    assert not Conversation.objects.exists() and not Message.objects.exists()
    assert not os.path.exists(path)


def test_assign_variants(staff_client, pj, conv, operator, operator2):
    url = f"{OP}conversations/{conv.pk}/assign/"
    assert pj(staff_client, url, {"operator_id": operator2.pk}).status_code == 200
    conv.refresh_from_db()
    assert conv.assigned_operator == operator2
    assert pj(staff_client, url, {}).status_code == 200  # self-assign
    conv.refresh_from_db()
    assert conv.assigned_operator == operator
    assert pj(staff_client, url, {"operator_id": None}).status_code == 200  # unassign
    conv.refresh_from_db()
    assert conv.assigned_operator is None
    assert pj(staff_client, url, {"operator_id": 9999}).status_code == 404


def test_update_subject_priority_ai(staff_client, pj, conv):
    url = f"{OP}conversations/{conv.pk}/update/"
    d = pj(staff_client, url, {"subject": "<b>Refund</b>", "priority": "high", "ai_enabled": False}).json()["conversation"]
    assert d["subject"] == "Refund" and d["priority"] == "high" and d["ai_enabled"] is False
    assert pj(staff_client, url, {"priority": "urgent"}).status_code == 400


def test_tags_set(staff_client, pj, conv):
    a, b = Tag.objects.create(name="A"), Tag.objects.create(name="B")
    url = f"{OP}conversations/{conv.pk}/tags/"
    d = pj(staff_client, url, {"tag_ids": [a.pk, b.pk]}).json()["conversation"]
    assert {t["name"] for t in d["tags"]} == {"A", "B"}
    assert pj(staff_client, url, {"tag_ids": "x"}).status_code == 400
    pj(staff_client, url, {"tag_ids": []})
    assert conv.tags.count() == 0


def test_block_visitor(staff_client, pj, guest_conv):
    assert pj(staff_client, f"{OP}conversations/{guest_conv.pk}/block/", {"reason": "spam"}).json()["ok"]
    b = BlockedVisitor.objects.get()
    assert b.guest_id == guest_conv.guest_id and b.ip_hash == guest_conv.ip_hash and b.reason == "spam"
    guest_conv.refresh_from_db()
    assert guest_conv.status == "closed"
    assert staff_client.post(f"{OP}api/blocked/{b.pk}/delete/").json()["ok"]
    assert not BlockedVisitor.objects.exists()


def test_operator_react_and_typing(staff_client, pj, conv, operator):
    sub = sse_manager.subscribe(str(conv.pk))
    msg = conv.messages.first()
    r = pj(staff_client, f"{OP}conversations/{conv.pk}/react/", {"message_id": msg.pk, "emoji": "👍"})
    assert r.json()["reactions"] == [{"emoji": "👍", "count": 1, "by": [f"operator:{operator.pk}"]}]
    assert sub.queue.get_nowait()["event"] == "reaction.updated"
    assert pj(staff_client, f"{OP}conversations/{conv.pk}/react/", {"message_id": msg.pk, "emoji": "💩"}).status_code == 400
    pj(staff_client, f"{OP}conversations/{conv.pk}/typing/", {"is_typing": True})
    ev = sub.queue.get_nowait()
    assert ev["event"] == "typing.start" and ev["data"]["sender_type"] == "operator"
    pj(staff_client, f"{OP}conversations/{conv.pk}/typing/", {"is_typing": False})
    assert sub.queue.get_nowait()["event"] == "typing.stop"


def test_transcript_download_with_notes(staff_client, conv):
    Message.objects.create(conversation=conv, sender_type="operator", text="private!", is_internal=True)
    plain = staff_client.get(f"{OP}conversations/{conv.pk}/transcript/").content.decode()
    full = staff_client.get(f"{OP}conversations/{conv.pk}/transcript/?notes=1").content.decode()
    assert "help me" in plain and "private!" not in plain
    assert "private!" in full and "internal note" in full


def test_transcript_email(staff_client, pj, guest_conv):
    assert pj(staff_client, f"{OP}conversations/{guest_conv.pk}/transcript/email/", {}).json()["ok"]
    assert mail.outbox[0].to == ["sara@example.com"] and "hi" in mail.outbox[0].body
    assert pj(staff_client, f"{OP}conversations/{guest_conv.pk}/transcript/email/", {"email": "nope"}).status_code == 400


def test_operator_stream_is_staff_firehose(staff_client, conv):
    r = staff_client.get(f"{OP}api/stream/")
    assert r["Content-Type"] == "text/event-stream"
    chunks = iter(r.streaming_content)
    next(chunks)
    assert b"__staff__" in next(chunks)
    r.close()


# ------------------------------------------------------- tags/canned/webhooks
def test_tag_crud(staff_client, pj):
    d = pj(staff_client, f"{OP}api/tags/", {"name": "Bug", "color": "#ff0000"}).json()
    assert d["tag"]["name"] == "Bug"
    assert pj(staff_client, f"{OP}api/tags/", {"name": "x", "color": "red"}).status_code == 400
    assert pj(staff_client, f"{OP}api/tags/", {"name": ""}).status_code == 400
    staff_client.post(f"{OP}api/tags/{d['tag']['id']}/delete/")
    assert not Tag.objects.exists()


def test_canned_crud(staff_client, pj):
    d = pj(staff_client, f"{OP}api/canned/", {"shortcut": "/Hello There", "text": "Hi!"}).json()
    assert d["canned"]["shortcut"] == "hello-there"
    d2 = pj(staff_client, f"{OP}api/canned/", {"shortcut": "hello-there", "text": "Updated"}).json()
    assert d2["canned"]["id"] == d["canned"]["id"] and CannedResponse.objects.get().text == "Updated"
    assert pj(staff_client, f"{OP}api/canned/", {"shortcut": "x"}).status_code == 400
    staff_client.post(f"{OP}api/canned/{d['canned']['id']}/delete/")
    assert not CannedResponse.objects.exists()


def test_webhook_test_endpoint(User, client, staff_client):
    w = WebhookEndpoint.objects.create(name="W", url="https://hooks.example.com/x")
    assert staff_client.post(f"{OP}api/webhooks/{w.pk}/test/").status_code == 403  # staff but not superuser
    client.force_login(User.objects.create_superuser("root", password="x"))
    with mock.patch("supchat.webhooks._send", return_value=204):
        d = client.post(f"{OP}api/webhooks/{w.pk}/test/").json()
    assert d["ok"] and d["status"] == 204
    assert client.post(f"{OP}api/webhooks/999/test/").status_code == 404


# ------------------------------------------------------------------ analytics
def test_analytics(staff_client, conv, guest_conv):
    from django.utils import timezone

    conv.rating = 4
    conv.first_response_at = conv.created_at + timezone.timedelta(seconds=90)
    conv.save()
    guest_conv.tags.add(Tag.objects.create(name="Bug"))
    d = staff_client.get(f"{OP}api/analytics/?days=7").json()
    assert len(d["labels"]) == len(d["conversations"]) == 7 and sum(d["conversations"]) == 2
    assert sum(d["messages"]) == 2 and len(d["hours"]) == 24
    assert d["rating"]["average"] == 4 and d["rating"]["distribution"][3] == 1
    assert round(d["first_response_seconds"]) == 90
    assert d["top_tags"][0]["name"] == "Bug"
    assert len(staff_client.get(f"{OP}api/analytics/?days=999").json()["labels"]) == 90
    assert len(staff_client.get(f"{OP}api/analytics/?days=x").json()["labels"]) == 7
