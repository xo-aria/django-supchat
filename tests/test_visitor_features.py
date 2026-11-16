"""Visitor-facing features added on top of the core chat API."""
import pytest
from django.core import mail
from django.test import Client

from supchat.models import BlockedVisitor, Conversation, Message, Reaction
from supchat.permissions import sign_guest_id
from supchat.sse import sse_manager

pytestmark = pytest.mark.django_db
B = "/supchat/"


def start(client, **extra):
    r = client.post(B + "start/", **extra)
    assert r.status_code == 200, r.content
    return r.json()["conversation"]["id"]


# ---------------------------------------------------------------- config/CSRF
def test_config_endpoint(client, sync_settings):
    sync_settings(TITLE="Help", QUICK_REPLIES=["Pricing"], LANGUAGES=["en", "fa", "xx"])
    d = client.get(B + "config/").json()
    assert d["title"] == "Help" and d["quick_replies"] == ["Pricing"] and d["languages"] == ["en", "fa"]
    assert "👍" in d["reactions"] and d["attachments"]["enabled"] is True and d["ai"] is False


def test_csrf_is_enforced_for_cookie_clients():
    c = Client(enforce_csrf_checks=True)
    assert c.post(B + "start/").status_code == 403


def test_csrf_passes_with_token():
    c = Client(enforce_csrf_checks=True)
    c.get(B + "config/")  # no cookie yet
    from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret

    secret = _get_new_csrf_string()
    c.cookies["csrftoken"] = secret
    assert c.post(B + "start/", HTTP_X_CSRFTOKEN=_mask_cipher_secret(secret)).status_code == 200


def test_mobile_header_token_flow():
    """Native clients get a token from /start/ and send it as a header (no cookies, no CSRF)."""
    c = Client(enforce_csrf_checks=True)
    c.cookies.clear()
    from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret

    secret = _get_new_csrf_string()
    c.cookies["csrftoken"] = secret
    r = c.post(B + "start/", HTTP_X_CSRFTOKEN=_mask_cipher_secret(secret), HTTP_X_SUPCHAT_CLIENT="ios")
    token, cid = r.json()["guest_token"], r.json()["conversation"]["id"]
    native = Client(enforce_csrf_checks=True)  # no cookies at all
    h = {"HTTP_X_SUPCHAT_GUEST": token}
    assert native.post(f"{B}conversations/{cid}/messages/", {"text": "from app"}, content_type="application/json", **h).status_code == 201
    assert native.get(f"{B}conversations/{cid}/messages/", **h).json()["messages"][0]["text"] == "from app"
    assert native.get(f"{B}conversations/{cid}/messages/", HTTP_X_SUPCHAT_GUEST="forged").status_code == 403


def test_browser_does_not_receive_token(client):
    assert "guest_token" not in client.post(B + "start/").json()


def test_start_stores_locale_and_fingerprint(client):
    cid = start(client, data={"locale": "fa"}, content_type="application/json", HTTP_USER_AGENT="Mozilla/5.0 test")
    c = Conversation.objects.get(pk=cid)
    assert c.locale == "fa" and c.user_agent == "Mozilla/5.0 test" and len(c.ip_hash) == 32


# ------------------------------------------------------------------ messages
def test_messages_pagination_returns_latest(client):
    cid = start(client)
    Message.objects.bulk_create([Message(conversation_id=cid, sender_type="guest", text=str(i)) for i in range(60)])
    d = client.get(f"{B}conversations/{cid}/messages/").json()
    assert len(d["messages"]) == 50 and d["has_more"] and d["messages"][-1]["text"] == "59"
    older = client.get(f"{B}conversations/{cid}/messages/?before={d['messages'][0]['id']}").json()
    assert [m["text"] for m in older["messages"]] == [str(i) for i in range(10)] and not older["has_more"]


def test_internal_notes_hidden_from_visitor(client, staff_client):
    cid = start(client)
    Message.objects.create(conversation_id=cid, sender_type="operator", text="secret", is_internal=True)
    Message.objects.create(conversation_id=cid, sender_type="operator", text="public")
    assert [m["text"] for m in client.get(f"{B}conversations/{cid}/messages/").json()["messages"]] == ["public"]


def test_visitor_cannot_post_internal_note(client, pj):
    cid = start(client)
    r = pj(client, f"{B}conversations/{cid}/messages/", {"text": "x", "internal": True})
    assert r.status_code == 201 and r.json()["message"]["is_internal"] is False


def test_reply_to(client, pj):
    cid = start(client)
    first = pj(client, f"{B}conversations/{cid}/messages/", {"text": "one"}).json()["message"]
    second = pj(client, f"{B}conversations/{cid}/messages/", {"text": "two", "reply_to": first["id"]}).json()["message"]
    assert second["reply_to"] == {"id": first["id"], "text": "one", "sender_type": "guest"}


def test_reply_to_internal_or_foreign_rejected(client, pj, user):
    cid = start(client)
    note = Message.objects.create(conversation_id=cid, sender_type="operator", text="n", is_internal=True)
    other = Message.objects.create(conversation=Conversation.objects.create(user=user), sender_type="user", text="o")
    for target in (note.pk, other.pk):
        assert pj(client, f"{B}conversations/{cid}/messages/", {"text": "x", "reply_to": target}).status_code == 400


def test_blocked_words(client, pj, sync_settings):
    sync_settings(BLOCKED_WORDS=["casino"])
    cid = start(client)
    assert pj(client, f"{B}conversations/{cid}/messages/", {"text": "Best CASINO bonus"}).status_code == 400


def test_message_cap(client, pj, sync_settings):
    sync_settings(MAX_MESSAGES_PER_CONVERSATION=1)
    cid = start(client)
    assert pj(client, f"{B}conversations/{cid}/messages/", {"text": "1"}).status_code == 201
    assert pj(client, f"{B}conversations/{cid}/messages/", {"text": "2"}).status_code == 400


# --------------------------------------------------------------- attachments
def test_upload_and_download_image(client, png):
    cid = start(client)
    r = client.post(f"{B}conversations/{cid}/messages/", {"text": "look", "file": png()})
    assert r.status_code == 201
    att = r.json()["message"]["attachment"]
    assert att["is_image"] and att["size"] > 0
    stored = Message.objects.get(pk=r.json()["message"]["id"]).attachment.name
    assert "pic" not in stored  # random stored name, the original is kept separately
    d = client.get(att["url"])
    assert d.status_code == 200 and d["X-Content-Type-Options"] == "nosniff"
    assert d["Content-Disposition"].startswith("inline") and "sandbox" in d["Content-Security-Policy"]
    assert client.get(att["url"] + "?download=1")["Content-Disposition"].startswith("attachment")
    d.close()


def test_attachment_access_control(client, png):
    cid = start(client)
    url = client.post(f"{B}conversations/{cid}/messages/", {"file": png()}).json()["message"]["attachment"]["url"]
    assert Client().get(url).status_code == 404
    assert client.get("/supchat/attachments/999999/").status_code == 404


def test_internal_attachment_hidden_from_visitor(client, staff_client, png):
    cid = start(client)
    r = staff_client.post(f"/supchat/operator/conversations/{cid}/send/", {"file": png(), "internal": "true"})
    url = r.json()["message"]["attachment"]["url"]
    assert client.get(url).status_code == 404
    resp = staff_client.get(url)
    assert resp.status_code == 200
    resp.close()


@pytest.mark.parametrize(
    "name,content",
    [
        ("evil.svg", b"<svg onload=alert(1)>"),
        ("page.html", b"<script>"),
        ("fake.png", b"GIF89a not a png"),
        ("run.exe", b"MZ"),
        ("empty.pdf", b""),
    ],
)
def test_bad_uploads_rejected(client, png, name, content):
    cid = start(client)
    assert client.post(f"{B}conversations/{cid}/messages/", {"file": png(name, content)}).status_code == 400


def test_upload_too_large(client, png, sync_settings):
    sync_settings(ATTACHMENT_MAX_MB=0.00001)
    cid = start(client)
    assert client.post(f"{B}conversations/{cid}/messages/", {"file": png()}).status_code == 400


def test_attachments_disabled(client, png, sync_settings):
    sync_settings(ATTACHMENTS=False)
    cid = start(client)
    assert client.post(f"{B}conversations/{cid}/messages/", {"file": png()}).status_code == 400


# ----------------------------------------------------- reactions/rating/etc
def test_visitor_reactions_toggle(client, pj):
    cid = start(client)
    m = Message.objects.create(conversation_id=cid, sender_type="operator", text="hi")
    url = f"{B}conversations/{cid}/react/"
    assert pj(client, url, {"message_id": m.pk, "emoji": "❤️"}).json()["reactions"] == [{"emoji": "❤️", "count": 1, "by": ["visitor"]}]
    assert pj(client, url, {"message_id": m.pk, "emoji": "❤️"}).json()["reactions"] == []
    assert pj(client, url, {"message_id": m.pk, "emoji": "x"}).status_code == 400
    assert pj(client, url, {"message_id": "abc", "emoji": "❤️"}).status_code == 400
    note = Message.objects.create(conversation_id=cid, sender_type="operator", text="n", is_internal=True)
    assert pj(client, url, {"message_id": note.pk, "emoji": "❤️"}).status_code == 400
    assert Reaction.objects.count() == 0


def test_rating_flow(client, pj, staff_client):
    cid = start(client)
    url = f"{B}conversations/{cid}/rate/"
    assert pj(client, url, {"rating": 9}).status_code == 400
    assert pj(client, url, {"rating": True}).status_code == 400
    assert pj(staff_client, url, {"rating": 5}).status_code == 403  # operators cannot rate
    assert pj(client, url, {"rating": 5, "comment": "<b>great</b>"}).json()["ok"]
    c = Conversation.objects.get(pk=cid)
    assert c.rating == 5 and c.rating_comment == "great"
    assert pj(client, url, {"rating": 4}).status_code == 400  # only once


def test_profile(client, pj):
    cid = start(client)
    url = f"{B}conversations/{cid}/profile/"
    d = pj(client, url, {"name": "<i>Ali</i>", "email": "ali@example.com"}).json()["conversation"]
    assert d["visitor_name"] == "Ali" and d["visitor_email"] == "ali@example.com"
    assert pj(client, url, {"name": "x", "email": "not-an-email"}).status_code == 400


def test_visitor_typing_broadcast(client, pj):
    cid = start(client)
    sub = sse_manager.subscribe(cid)
    assert pj(client, f"{B}conversations/{cid}/typing/", {"is_typing": True}).json()["ok"]
    ev = sub.queue.get_nowait()
    assert ev["event"] == "typing.start" and ev["data"]["sender_type"] == "guest"


def test_visitor_transcript_download(client, pj):
    cid = start(client)
    pj(client, f"{B}conversations/{cid}/messages/", {"text": "hello there"})
    Message.objects.create(conversation_id=cid, sender_type="operator", text="secret", is_internal=True)
    body = client.get(f"{B}conversations/{cid}/transcript/").content.decode()
    assert "hello there" in body and "secret" not in body
    assert Client().get(f"{B}conversations/{cid}/transcript/").status_code == 403


def test_transcript_email_only_to_own_address(client, pj):
    cid = start(client)
    url = f"{B}conversations/{cid}/transcript/email/"
    assert pj(client, url, {}).status_code == 400  # no address yet
    assert pj(client, url, {"email": "me@example.com"}).json()["ok"]
    assert mail.outbox[-1].to == ["me@example.com"]
    # once an address is stored, a different one is refused (no spam relay)
    assert pj(client, url, {"email": "victim@example.com"}).status_code == 400


def test_transcript_email_rate_limited(client, pj, sync_settings):
    sync_settings(TRANSCRIPT_RATE_LIMIT={"COUNT": 1, "WINDOW": 60})
    cid = start(client)
    url = f"{B}conversations/{cid}/transcript/email/"
    assert pj(client, url, {"email": "me@example.com"}).status_code == 200
    assert pj(client, url, {}).status_code == 403


# ------------------------------------------------------------------- safety
def test_blocked_guest_cannot_start_or_send(client, pj):
    cid = start(client)
    conv = Conversation.objects.get(pk=cid)
    BlockedVisitor.objects.create(guest_id=conv.guest_id)
    assert pj(client, f"{B}conversations/{cid}/messages/", {"text": "x"}).status_code == 403
    conv.status = "closed"
    conv.save()
    assert client.post(B + "start/").status_code == 403


def test_blocked_ip(pj):
    c = Client(REMOTE_ADDR="9.9.9.9")
    cid = start(c)
    conv = Conversation.objects.get(pk=cid)
    BlockedVisitor.objects.create(ip_hash=conv.ip_hash)
    assert Client(REMOTE_ADDR="9.9.9.9").post(B + "start/").status_code == 403
    assert Client(REMOTE_ADDR="8.8.8.8").post(B + "start/").status_code == 200


def test_max_open_per_ip_counts_only_real_conversations(sync_settings):
    sync_settings(MAX_OPEN_PER_IP=2)
    # opening the widget without writing does not use up the quota
    for _ in range(3):
        assert Client(REMOTE_ADDR="1.2.3.4").post(B + "start/").status_code == 200
    for _ in range(2):
        c = Client(REMOTE_ADDR="1.2.3.4")
        cid = start(c)
        c.post(f"{B}conversations/{cid}/messages/", {"text": "hi"}, content_type="application/json")
    assert Client(REMOTE_ADDR="1.2.3.4").post(B + "start/").status_code == 403
    assert Client(REMOTE_ADDR="5.6.7.8").post(B + "start/").status_code == 200


def test_forwarded_for_ignored_unless_trusted(rf, sync_settings):
    from supchat.permissions import client_ip

    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="1.1.1.1")
    assert client_ip(req) == "1.1.1.1"
    sync_settings(TRUST_PROXY_HEADERS=True)
    assert client_ip(req) == "6.6.6.6"


def test_closed_event_reaches_visitor(client):
    cid = start(client)
    sub = sse_manager.subscribe(cid)
    client.post(f"{B}conversations/{cid}/close/")
    assert sub.queue.get_nowait()["event"] == "conversation.closed"


def test_guest_header_ignored_when_signature_invalid(client):
    cid = start(client)
    other = Client()
    assert other.get(f"{B}conversations/{cid}/messages/", HTTP_X_SUPCHAT_GUEST=sign_guest_id("someone-else")).status_code == 403


@pytest.mark.parametrize(
    "name,content,ok",
    [
        ("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", True),
        ("b.webp", b"RIFF\x00\x00\x00\x00AVI LIST", False),
        ("notes.txt", "سلام plain text".encode(), True),
        ("bin.txt", b"abc\x00def", False),
        ("doc.pdf", b"%PDF-1.7 ...", True),
    ],
)
def test_upload_magic_bytes(client, png, name, content, ok):
    cid = start(client)
    r = client.post(f"{B}conversations/{cid}/messages/", {"file": png(name, content)})
    assert (r.status_code == 201) is ok


def test_persian_attachment_filename_is_encoded(client, png):
    cid = start(client)
    r = client.post(f"{B}conversations/{cid}/messages/", {"file": png("فاکتور.png")})
    att = r.json()["message"]["attachment"]
    assert att["name"] == "فاکتور.png"
    d = client.get(att["url"] + "?download=1")
    assert "filename*=utf-8''" in d["Content-Disposition"]
    d.close()


def test_conversation_email_cannot_be_swapped(client, pj):
    cid = start(client)
    url = f"{B}conversations/{cid}/profile/"
    assert pj(client, url, {"name": "A", "email": "a@example.com"}).status_code == 200
    assert pj(client, url, {"name": "A2", "email": "a@example.com"}).status_code == 200  # name can change
    assert pj(client, url, {"name": "A", "email": "victim@example.com"}).status_code == 400


def test_guest_rate_limit_is_per_guest_not_per_ip(sync_settings, pj):
    sync_settings(RATE_LIMIT={"MESSAGES": 1, "WINDOW": 60})
    a, b = Client(REMOTE_ADDR="10.0.0.1"), Client(REMOTE_ADDR="10.0.0.1")  # same proxy IP
    ca, cb = start(a), start(b)
    assert pj(a, f"{B}conversations/{ca}/messages/", {"text": "1"}).status_code == 201
    assert pj(b, f"{B}conversations/{cb}/messages/", {"text": "1"}).status_code == 201
    assert pj(a, f"{B}conversations/{ca}/messages/", {"text": "2"}).status_code == 403


def test_blocked_logged_in_user(user_client, staff_client, pj, user):
    cid = start(user_client)
    pj(user_client, f"{B}conversations/{cid}/messages/", {"text": "spam"})
    assert pj(staff_client, f"/supchat/operator/conversations/{cid}/block/", {}).json()["ok"]
    b = BlockedVisitor.objects.get()
    assert b.user == user and b.ip_hash == ""
    assert user_client.post(B + "start/").status_code == 403
    assert Client().post(B + "start/").status_code == 200  # same IP, other visitors unaffected


def test_staff_announced_on_first_message_not_on_open(client, pj):
    from supchat.sse import STAFF_CHANNEL

    fire = sse_manager.subscribe(STAFF_CHANNEL, staff=True)
    cid = start(client)
    assert fire.queue.empty()
    pj(client, f"{B}conversations/{cid}/messages/", {"text": "hello"})
    events = [fire.queue.get_nowait()["event"] for _ in range(fire.queue.qsize())]
    assert events.count("conversation.created") == 1
    pj(client, f"{B}conversations/{cid}/messages/", {"text": "again"})
    events = [fire.queue.get_nowait()["event"] for _ in range(fire.queue.qsize())]
    assert "conversation.created" not in events
