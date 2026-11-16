import uuid

import pytest

from supchat.models import Message

pytestmark = pytest.mark.django_db


def start(client):
    r = client.post("/supchat/start/")
    assert r.status_code == 200
    return r.json()["conversation"]["id"]


def test_start_requires_post(guest_client):
    assert guest_client.get("/supchat/start/").status_code == 405


def test_start_guest_sets_cookie(guest_client):
    cid = start(guest_client)
    cookie = guest_client.cookies["supchat_guest"]
    assert cookie["httponly"]
    assert start(guest_client) == cid


def test_start_guest_disabled(guest_client, settings):
    settings.SUPCHAT = {"ALLOW_GUEST": False}
    assert guest_client.post("/supchat/start/").status_code == 403


def test_start_for_user_no_cookie(user_client):
    start(user_client)
    assert "supchat_guest" not in user_client.cookies


def test_guest_send_and_list(guest_client, pj):
    cid = start(guest_client)
    url = f"/supchat/conversations/{cid}/messages/"
    r = pj(guest_client, url, {"text": "hello"})
    assert r.status_code == 201
    assert r.json()["message"]["sender_type"] == "guest"
    msgs = guest_client.get(url).json()["messages"]
    assert [m["text"] for m in msgs] == ["hello"]


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "   "}, {"text": "<p></p>"}])
def test_send_invalid(guest_client, pj, payload):
    cid = start(guest_client)
    r = pj(guest_client, f"/supchat/conversations/{cid}/messages/", payload)
    assert r.status_code == 400


def test_send_too_long(guest_client, pj, settings):
    settings.SUPCHAT = {"MAX_MESSAGE_LENGTH": 3}
    cid = start(guest_client)
    assert pj(guest_client, f"/supchat/conversations/{cid}/messages/", {"text": "abcd"}).status_code == 400


def test_send_bad_json(guest_client):
    cid = start(guest_client)
    url = f"/supchat/conversations/{cid}/messages/"
    assert guest_client.post(url, data="{nope", content_type="application/json").status_code == 400
    assert guest_client.post(url, data="[1]", content_type="application/json").status_code == 400


def test_xss_is_stripped(guest_client, pj):
    cid = start(guest_client)
    r = pj(guest_client, f"/supchat/conversations/{cid}/messages/", {"text": "<img src=x onerror=alert(1)>hi"})
    assert r.json()["message"]["text"] == "hi"


def test_other_user_cannot_access(user_client, other_client, pj):
    cid = start(user_client)
    url = f"/supchat/conversations/{cid}/messages/"
    assert other_client.get(url).status_code == 403
    assert pj(other_client, url, {"text": "x"}).status_code == 403
    assert other_client.post(f"/supchat/conversations/{cid}/close/").status_code == 403
    assert other_client.get(f"/supchat/conversations/{cid}/events/").status_code == 404


def test_other_guest_cannot_access(guest_client, client):
    cid = start(guest_client)
    start(client)  # different guest identity
    assert client.get(f"/supchat/conversations/{cid}/messages/").status_code == 403


def test_forged_guest_cookie_rejected(guest_client, client):
    cid = start(guest_client)
    client.cookies["supchat_guest"] = "forged"
    assert client.get(f"/supchat/conversations/{cid}/messages/").status_code == 403


def test_unknown_conversation(guest_client):
    assert guest_client.get(f"/supchat/conversations/{uuid.uuid4()}/messages/").status_code == 403


def test_close_blocks_new_messages(guest_client, pj):
    cid = start(guest_client)
    assert guest_client.post(f"/supchat/conversations/{cid}/close/").status_code == 200
    r = pj(guest_client, f"/supchat/conversations/{cid}/messages/", {"text": "x"})
    assert r.status_code == 403


def test_mark_read(user_client, pj):
    cid = start(user_client)
    Message.objects.create(conversation_id=cid, sender_type="operator", text="a")
    url = f"/supchat/conversations/{cid}/read/"
    assert pj(user_client, url, {}).json()["count"] == 1
    assert pj(user_client, url, {}).json()["count"] == 0


def test_mark_read_ids_validation(user_client, pj):
    cid = start(user_client)
    url = f"/supchat/conversations/{cid}/read/"
    assert pj(user_client, url, {"message_ids": ["a"]}).status_code == 400
    assert pj(user_client, url, {"message_ids": "x"}).status_code == 400
    assert pj(user_client, url, {"message_ids": [1, 2]}).status_code == 200


def test_events_stream(guest_client):
    cid = start(guest_client)
    r = guest_client.get(f"/supchat/conversations/{cid}/events/")
    assert r.status_code == 200
    assert r["Content-Type"] == "text/event-stream"
    first = next(iter(r.streaming_content)).decode()
    assert first.startswith("retry:")
    r.close()


def test_rate_limited_view(guest_client, pj, settings):
    settings.SUPCHAT = {"RATE_LIMIT": {"MESSAGES": 1, "WINDOW": 60}}
    cid = start(guest_client)
    url = f"/supchat/conversations/{cid}/messages/"
    assert pj(guest_client, url, {"text": "1"}).status_code == 201
    assert pj(guest_client, url, {"text": "2"}).status_code == 403
