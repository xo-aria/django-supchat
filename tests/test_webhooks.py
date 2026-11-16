import hashlib
import hmac
import json
import socket
from unittest import mock

import pytest

from supchat import webhooks
from supchat.models import Conversation, WebhookEndpoint

pytestmark = pytest.mark.django_db
DATA = {"conversation": "c1", "participant": "Ali", "text": "hello", "status": "open"}


def test_generic_payload_is_signed():
    ep = WebhookEndpoint(name="g", url="https://x.example", secret="s3cret")
    raw, headers = webhooks.build_request(ep, "message.created", DATA)
    body = json.loads(raw)
    assert body["event"] == "message.created" and body["data"] == DATA
    expected = hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
    assert headers["X-Supchat-Signature"] == f"sha256={expected}"


def test_slack_and_discord_payloads():
    raw, headers = webhooks.build_request(WebhookEndpoint(kind="slack", url="https://x"), "message.created", DATA)
    assert json.loads(raw) == {"text": "Ali: hello"} and "X-Supchat-Signature" not in headers
    raw, _ = webhooks.build_request(WebhookEndpoint(kind="discord", url="https://x"), "conversation.rated", {**DATA, "rating": 5})
    assert json.loads(raw) == {"content": "Ali rated the conversation 5/5"}


@pytest.mark.parametrize("event", webhooks.EVENTS)
def test_summaries(event):
    assert webhooks.summarize(event, DATA)


def test_event_filter():
    ep = WebhookEndpoint(events="conversation.started, conversation.closed")
    assert ep.wants("conversation.closed") and not ep.wants("message.created")
    assert WebhookEndpoint(events="*").wants("anything")


def _resolve(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254"])
def test_ssrf_guard_blocks_private_targets(ip):
    with mock.patch("socket.getaddrinfo", return_value=_resolve(ip)):
        with pytest.raises(webhooks.UnsafeURL):
            webhooks.check_url("https://internal.example/hook")


def test_ssrf_guard_allows_public_and_opt_out(sync_settings):
    with mock.patch("socket.getaddrinfo", return_value=_resolve("93.184.216.34")):
        webhooks.check_url("https://hooks.example.com/x")
    with pytest.raises(webhooks.UnsafeURL):
        webhooks.check_url("ftp://hooks.example.com/x")
    sync_settings(WEBHOOK_ALLOW_PRIVATE=True)
    webhooks.check_url("http://localhost:9000/hook")


def test_deliver_records_status_and_errors():
    ep = WebhookEndpoint.objects.create(name="x", url="https://hooks.example.com/x")
    with mock.patch("supchat.webhooks._send", return_value=500):
        webhooks.deliver(ep, "message.created", DATA)
    ep.refresh_from_db()
    assert ep.last_status == 500 and ep.last_error == "HTTP 500" and ep.last_at
    with mock.patch("supchat.webhooks._send", side_effect=webhooks.UnsafeURL("nope")):
        webhooks.deliver(ep, "message.created", DATA)
    ep.refresh_from_db()
    assert ep.last_status is None and ep.last_error == "nope"


def test_dispatch_respects_active_and_events():
    WebhookEndpoint.objects.create(name="a", url="https://a.example", events="*")
    WebhookEndpoint.objects.create(name="b", url="https://b.example", events="conversation.closed")
    WebhookEndpoint.objects.create(name="c", url="https://c.example", is_active=False)
    with mock.patch("supchat.webhooks._send", return_value=200) as send:
        assert webhooks.dispatch("message.created", DATA) == 1
    assert send.call_args.args[0] == "https://a.example"


def test_send_message_fires_webhook_after_commit(client, pj, django_capture_on_commit_callbacks):
    WebhookEndpoint.objects.create(name="a", url="https://a.example", kind="slack")
    with mock.patch("supchat.webhooks._send", return_value=200) as send:
        with django_capture_on_commit_callbacks(execute=True):
            cid = client.post("/supchat/start/").json()["conversation"]["id"]
        with django_capture_on_commit_callbacks(execute=True):
            pj(client, f"/supchat/conversations/{cid}/messages/", {"text": "hey"})
    bodies = [json.loads(c.args[1]) for c in send.call_args_list]
    assert {"text": "New support conversation from " + Conversation.objects.get().display_name} in bodies
    assert any("hey" in b["text"] for b in bodies)


def test_internal_notes_do_not_fire_webhooks(staff_client, pj, user, django_capture_on_commit_callbacks):
    c = Conversation.objects.create(user=user)
    WebhookEndpoint.objects.create(name="a", url="https://a.example")
    with mock.patch("supchat.webhooks._send", return_value=200) as send:
        with django_capture_on_commit_callbacks(execute=True):
            pj(staff_client, f"/supchat/operator/conversations/{c.pk}/send/", {"text": "note", "internal": True})
    send.assert_not_called()


def test_real_send_uses_no_redirect_opener():
    ep = WebhookEndpoint(url="https://hooks.example.com/x")
    raw, headers = webhooks.build_request(ep, "message.created", DATA)
    resp = mock.MagicMock()
    resp.__enter__.return_value.status = 204
    opener = mock.MagicMock()
    opener.open.return_value = resp
    with mock.patch("socket.getaddrinfo", return_value=_resolve("93.184.216.34")), mock.patch(
        "urllib.request.build_opener", return_value=opener
    ) as build:
        assert webhooks._send(ep.url, raw, headers, 1) == 204
    assert build.call_args.args[0] is webhooks._NoRedirect
