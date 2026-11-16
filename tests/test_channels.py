"""Optional WebSocket adapter. Skipped when Django Channels is not installed."""
import pytest

pytest.importorskip("channels")

from asgiref.sync import sync_to_async  # noqa: E402
from channels.routing import URLRouter  # noqa: E402
from channels.testing.websocket import WebsocketCommunicator  # noqa: E402
from django.contrib.auth.models import AnonymousUser  # noqa: E402

from supchat.contrib.channels import websocket_urlpatterns  # noqa: E402
from supchat.models import Conversation  # noqa: E402
from supchat.permissions import sign_guest_id  # noqa: E402
from supchat.sse import sse_manager  # noqa: E402

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]


def app_for(user=None):
    router = URLRouter(websocket_urlpatterns)

    async def app(scope, receive, send):
        scope = dict(scope, user=user or AnonymousUser())
        return await router(scope, receive, send)

    return app


async def test_visitor_receives_public_events_only():
    conv = await sync_to_async(Conversation.objects.create)(guest_id="g1")
    cookie = f"supchat_guest={sign_guest_id('g1')}".encode()
    comm = WebsocketCommunicator(app_for(), f"/ws/supchat/{conv.pk}/", headers=[(b"cookie", cookie)])
    connected, _ = await comm.connect()
    assert connected
    assert (await comm.receive_json_from())["event"] == "connected"
    sse_manager.broadcast(str(conv.pk), "note", {"secret": True}, internal=True)
    sse_manager.broadcast(str(conv.pk), "message.created", {"text": "hi"})
    msg = await comm.receive_json_from(timeout=5)
    assert msg == {"event": "message.created", "data": {"text": "hi"}}
    await comm.disconnect()


async def test_visitor_typing_frame_is_broadcast():
    conv = await sync_to_async(Conversation.objects.create)(guest_id="g2")
    comm = WebsocketCommunicator(app_for(), f"/ws/supchat/{conv.pk}/", headers=[(b"x-supchat-guest", sign_guest_id("g2").encode())])
    assert (await comm.connect())[0]
    await comm.receive_json_from()
    await comm.send_json_to({"type": "typing", "is_typing": True})
    msg = await comm.receive_json_from(timeout=5)
    assert msg["event"] == "typing.start" and msg["data"]["sender_type"] == "guest"
    await comm.disconnect()


async def test_stranger_is_rejected():
    conv = await sync_to_async(Conversation.objects.create)(guest_id="g3")
    comm = WebsocketCommunicator(app_for(), f"/ws/supchat/{conv.pk}/")
    connected, code = await comm.connect()
    assert not connected and code == 4403


async def test_staff_firehose(django_user_model):
    staff = await sync_to_async(django_user_model.objects.create_user)("op", is_staff=True)
    comm = WebsocketCommunicator(app_for(staff), "/ws/supchat/operator/")
    assert (await comm.connect())[0]
    await comm.receive_json_from()
    sse_manager.broadcast("any-conversation", "note", {"x": 1}, internal=True)
    assert (await comm.receive_json_from(timeout=5))["event"] == "note"
    await comm.disconnect()
    denied = WebsocketCommunicator(app_for(), "/ws/supchat/operator/")
    assert not (await denied.connect())[0]
