import json
from unittest import mock

import pytest

from supchat import ai
from supchat.models import Conversation, Message

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai_on(sync_settings):
    def apply(**kw):
        sync_settings(AI={"ENABLED": True, "PROVIDER": "openai", "API_KEY": "sk-test", "MODEL": "gpt-test", **kw})

    apply()
    return apply


def fake_openai(text="Hello from AI"):
    return {"choices": [{"message": {"content": text}}]}


def fake_anthropic(text="Hello from Anthropic"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def guest_conversation(client):
    cid = client.post("/supchat/start/").json()["conversation"]["id"]
    return Conversation.objects.get(pk=cid)


def say(client, conv, text, pj):
    return pj(client, f"/supchat/conversations/{conv.pk}/messages/", {"text": text})


# ------------------------------------------------------------------ history
def test_build_messages_roles_merging_and_privacy(user):
    c = Conversation.objects.create(user=user)
    for st, text, internal in [
        ("operator", "greeting before user", False),
        ("user", "hi", False),
        ("user", "are you there?", False),
        ("operator", "secret note", True),
        ("bot", "yes!", False),
        ("system", "joined", False),
    ]:
        Message.objects.create(conversation=c, sender_type=st, text=text, is_internal=internal)
    assert ai.build_messages(c, 20) == [
        {"role": "user", "content": "hi\nare you there?"},
        {"role": "assistant", "content": "yes!"},
    ]


def test_build_messages_limit(user):
    c = Conversation.objects.create(user=user)
    for i in range(10):
        Message.objects.create(conversation=c, sender_type="user", text=str(i))
    assert ai.build_messages(c, 3) == [{"role": "user", "content": "7\n8\n9"}]


# ---------------------------------------------------------------- providers
def test_openai_request_shape(ai_on, user):
    ai_on(BASE_URL="https://api.groq.example/openai/v1/")
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value=fake_openai("yo")) as post:
        assert ai.generate_reply(c) == "yo"
    url, headers, body, timeout = post.call_args.args
    assert url == "https://api.groq.example/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "gpt-test" and body["messages"][0]["role"] == "system" and body["messages"][-1]["content"] == "hi"


def test_anthropic_request_shape(ai_on, user):
    ai_on(PROVIDER="anthropic", API_KEY="ak-test", MODEL="test-model")
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value=fake_anthropic("answer")) as post:
        assert ai.generate_reply(c) == "answer"
    url, headers, body, _ = post.call_args.args
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "ak-test" and headers["anthropic-version"] == ai.ANTHROPIC_VERSION
    assert body["system"] and body["messages"] == [{"role": "user", "content": "hi"}] and body["max_tokens"] == 1024


def test_anthropic_refusal_is_an_error(ai_on, user):
    ai_on(PROVIDER="anthropic", MODEL="m")
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value={"content": [], "stop_reason": "refusal"}):
        with pytest.raises(ai.AIError):
            ai.generate_reply(c)


def custom_bot(messages, conversation):
    return f"echo: {messages[-1]['content']}"


def test_custom_callable(ai_on, user):
    ai_on(PROVIDER="custom", CALLABLE="tests.test_ai.custom_bot", MODEL="")
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="ping")
    assert ai.generate_reply(c) == "echo: ping"


@pytest.mark.parametrize("cfg", [{"MODEL": ""}, {"PROVIDER": "nope"}, {"PROVIDER": "custom", "CALLABLE": None}])
def test_misconfiguration_raises(ai_on, user, cfg):
    ai_on(**cfg)
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with pytest.raises(ai.AIError):
        ai.generate_reply(c)


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"message": None}]}])
def test_bad_openai_shapes(ai_on, user, payload):
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value=payload):
        with pytest.raises(ai.AIError):
            ai.generate_reply(c)


def test_http_errors_wrapped():
    import urllib.error

    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        with pytest.raises(ai.AIError):
            ai._http_post("https://x.invalid", {}, {}, 1)
    err = urllib.error.HTTPError("https://x", 401, "no", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(ai.AIError, match="401"):
            ai._http_post("https://x.invalid", {}, {}, 1)


def test_http_post_success():
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps({"ok": 1}).encode()
    with mock.patch("urllib.request.urlopen", return_value=resp):
        assert ai._http_post("https://x.invalid", {}, {}, 1) == {"ok": 1}


# --------------------------------------------------------------- end-to-end
def test_auto_reply_end_to_end(ai_on, client, pj, django_capture_on_commit_callbacks):
    conv = guest_conversation(client)
    with mock.patch("supchat.ai._http_post", return_value=fake_openai("Sure, I can help")):
        with django_capture_on_commit_callbacks(execute=True):
            assert say(client, conv, "I need help", pj).status_code == 201
    bot = Message.objects.filter(conversation=conv, sender_type="bot").get()
    assert bot.text == "Sure, I can help"
    msgs = client.get(f"/supchat/conversations/{conv.pk}/messages/").json()["messages"]
    assert msgs[-1]["sender_name"] == "Assistant"


def test_bot_does_not_answer_itself_or_operators(ai_on, user):
    c = Conversation.objects.create(user=user)
    bot = Message.objects.create(conversation=c, sender_type="bot", text="hi")
    with mock.patch("supchat.ai._http_post") as post:
        assert ai.maybe_auto_reply(c.pk, bot.pk) is None
    post.assert_not_called()


def test_operator_reply_disables_bot(ai_on, client, pj, staff_client, django_capture_on_commit_callbacks):
    conv = guest_conversation(client)
    pj(staff_client, f"/supchat/operator/conversations/{conv.pk}/send/", {"text": "Human here"})
    conv.refresh_from_db()
    assert conv.ai_enabled is False
    with mock.patch("supchat.ai._http_post") as post:
        with django_capture_on_commit_callbacks(execute=True):
            say(client, conv, "thanks", pj)
    post.assert_not_called()


def test_handoff_keyword(ai_on, client, pj, django_capture_on_commit_callbacks):
    conv = guest_conversation(client)
    with mock.patch("supchat.ai._http_post") as post:
        with django_capture_on_commit_callbacks(execute=True):
            say(client, conv, "Can I talk to a human please?", pj)
    post.assert_not_called()
    conv.refresh_from_db()
    assert conv.ai_enabled is False
    assert Message.objects.filter(conversation=conv, sender_type="bot").count() == 1


def test_provider_failure_is_silent(ai_on, client, pj, django_capture_on_commit_callbacks):
    conv = guest_conversation(client)
    with mock.patch("supchat.ai._http_post", side_effect=ai.AIError("boom")):
        with django_capture_on_commit_callbacks(execute=True):
            assert say(client, conv, "hello", pj).status_code == 201
    assert not Message.objects.filter(sender_type="bot").exists()


def test_disabled_ai_never_called(client, pj, django_capture_on_commit_callbacks):
    conv = guest_conversation(client)
    with mock.patch("supchat.ai._http_post") as post:
        with django_capture_on_commit_callbacks(execute=True):
            say(client, conv, "hello", pj)
    post.assert_not_called()


def test_closed_conversation_not_answered(ai_on, user):
    c = Conversation.objects.create(user=user, status="closed")
    m = Message.objects.create(conversation=c, sender_type="user", text="hi")
    assert ai.maybe_auto_reply(c.pk, m.pk) is None
    assert ai.maybe_auto_reply(c.pk, 999999) is None


def test_token_param_and_extra_body(ai_on, user):
    ai_on(TOKEN_PARAM="max_completion_tokens", EXTRA_BODY={"temperature": 0.2})
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value=fake_openai()) as post:
        ai.generate_reply(c)
    body = post.call_args.args[2]
    assert body["max_completion_tokens"] == 1024 and "max_tokens" not in body and body["temperature"] == 0.2


def test_anthropic_extra_body(ai_on, user):
    ai_on(PROVIDER="anthropic", MODEL="m", EXTRA_BODY={"output_config": {"effort": "low"}})
    c = Conversation.objects.create(user=user)
    Message.objects.create(conversation=c, sender_type="user", text="hi")
    with mock.patch("supchat.ai._http_post", return_value=fake_anthropic()) as post:
        ai.generate_reply(c)
    assert post.call_args.args[2]["output_config"] == {"effort": "low"}
