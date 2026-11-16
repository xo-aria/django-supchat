"""SSE audience scoping, background runner, cleanup command, admin, i18n parity."""
import re
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from supchat import tasks
from supchat.models import Conversation, Message
from supchat.sse import STAFF_CHANNEL, SSEManager

STATIC = Path(__file__).resolve().parent.parent / "supchat" / "static" / "supchat"


# -------------------------------------------------------------------- SSE
def test_internal_events_only_reach_staff():
    m = SSEManager()
    visitor, staff_conv, firehose = m.subscribe("c1"), m.subscribe("c1", staff=True), m.subscribe(STAFF_CHANNEL, staff=True)
    m.broadcast("c1", "message.created", {"x": 1}, internal=True)
    assert visitor.queue.empty()
    assert staff_conv.queue.get_nowait()["event"] == "message.created"
    assert firehose.queue.get_nowait()["event"] == "message.created"
    m.broadcast("c1", "message.created", {"x": 2})
    assert visitor.queue.get_nowait()["data"] == {"x": 2}


def test_firehose_receives_every_conversation():
    m = SSEManager()
    fire = m.subscribe(STAFF_CHANNEL, staff=True)
    m.broadcast("a", "e", {})
    m.broadcast("b", "e", {})
    assert fire.queue.qsize() == 2


def hook_calls(*args):
    hook_calls.calls.append(args)


hook_calls.calls = []


def test_broadcast_hook(sync_settings):
    sync_settings(BROADCAST_HOOK="tests.test_misc.hook_calls")
    hook_calls.calls.clear()
    SSEManager().broadcast("c1", "e", {"a": 1}, internal=True)
    assert hook_calls.calls == [("c1", "e", {"a": 1}, True)]


def test_broken_broadcast_hook_is_swallowed(sync_settings):
    sync_settings(BROADCAST_HOOK=mock.Mock(side_effect=RuntimeError("redis down")))
    m = SSEManager()
    c = m.subscribe("c1")
    m.broadcast("c1", "e", {})
    assert not c.queue.empty()


# ----------------------------------------------------------- background
@pytest.mark.django_db
def test_background_thread_mode(settings, django_capture_on_commit_callbacks):
    settings.SUPCHAT = {"BACKGROUND": "thread"}
    done = []
    with mock.patch("threading.Thread") as thread:
        with django_capture_on_commit_callbacks(execute=True):
            tasks.run_after_commit(done.append, 1)
    thread.assert_called_once()
    assert thread.return_value.start.called and done == []


@pytest.mark.django_db
def test_background_errors_are_logged_not_raised(django_capture_on_commit_callbacks, caplog):
    def boom():
        raise RuntimeError("x")

    with django_capture_on_commit_callbacks(execute=True):
        tasks.run_after_commit(boom)
    assert "background task" in caplog.text


# --------------------------------------------------------------- cleanup
@pytest.mark.django_db
def test_cleanup_command(sync_settings, user, png):
    sync_settings(AUTO_CLOSE_AFTER_HOURS=2, RETENTION_DAYS=30)
    now = timezone.now()
    idle = Conversation.objects.create(user=user, last_message_at=now - timedelta(hours=5))
    fresh = Conversation.objects.create(user=user, last_message_at=now)
    old = Conversation.objects.create(user=user, status="closed", closed_at=now - timedelta(days=60))
    m = Message(conversation=old, sender_type="user")
    m.attachment.save("a.png", png(), save=True)
    path = m.attachment.path

    out = StringIO()
    call_command("supchat_cleanup", "--dry-run", stdout=out)
    assert "closed=1 purged=1" in out.getvalue() and Conversation.objects.count() == 3

    call_command("supchat_cleanup", stdout=StringIO())
    idle.refresh_from_db()
    fresh.refresh_from_db()
    assert idle.status == "closed" and fresh.status == "open"
    assert not Conversation.objects.filter(pk=old.pk).exists()
    assert not Path(path).exists()


@pytest.mark.django_db
def test_cleanup_disabled_by_default():
    out = StringIO()
    call_command("supchat_cleanup", stdout=out)
    assert "closed=0 purged=0" in out.getvalue()


# ------------------------------------------------------------------ admin
@pytest.mark.django_db
@pytest.mark.parametrize("model", ["conversation", "message", "operator", "tag", "cannedresponse", "webhookendpoint", "blockedvisitor", "reaction"])
def test_admin_changelists(client, User, model, user):
    Conversation.objects.create(user=user)
    client.force_login(User.objects.create_superuser("root", password="x"))
    assert client.get(f"/admin/supchat/{model}/").status_code == 200


# ------------------------------------------------------------------ i18n
def _lang_keys(src: str, lang: str) -> set[str]:
    block = re.search(rf"\n    {lang}: \{{(.*?)\n    \}}", src, re.S).group(1)
    return set(re.findall(r"(\w+): '", block))


def test_i18n_en_and_fa_are_complete():
    src = (STATIC / "i18n.js").read_text(encoding="utf-8")
    en, fa = _lang_keys(src, "en"), _lang_keys(src, "fa")
    assert en and en == fa


def test_i18n_keys_used_in_js_exist():
    src = (STATIC / "i18n.js").read_text(encoding="utf-8")
    en = _lang_keys(src, "en")
    used = set()
    for name in ("supchat.js", "operator.js"):
        used |= set(re.findall(r"\bt\('(\w+)'", (STATIC / name).read_text(encoding="utf-8")))
    assert used - en == set()


def test_i18n_every_language_declared():
    src = (STATIC / "i18n.js").read_text(encoding="utf-8")
    from supchat.conf import LANGUAGES

    for lang in LANGUAGES:
        assert f"\n    {lang}: {{" in src
        assert len(_lang_keys(src, lang)) > 100
