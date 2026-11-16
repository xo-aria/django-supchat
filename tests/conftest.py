import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory

from supchat.models import Operator
from supchat.sse import sse_manager


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")


@pytest.fixture(autouse=True)
def _clean_state():
    cache.clear()
    sse_manager._connections.clear()
    yield
    cache.clear()
    sse_manager._connections.clear()


@pytest.fixture
def User():
    return get_user_model()


@pytest.fixture
def user(User):
    return User.objects.create_user("alice", password="pw")


@pytest.fixture
def other_user(User):
    return User.objects.create_user("bob", password="pw")


@pytest.fixture
def staff(User):
    return User.objects.create_user("staff", password="pw", is_staff=True)


@pytest.fixture
def operator(staff):
    return Operator.objects.create(user=staff)


@pytest.fixture
def operator2(User):
    u = User.objects.create_user("op2", password="pw", is_staff=True)
    return Operator.objects.create(user=u)


@pytest.fixture
def guest_client():
    return Client()


@pytest.fixture
def user_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def other_client(other_user):
    c = Client()
    c.force_login(other_user)
    return c


@pytest.fixture
def staff_client(staff, operator):
    c = Client()
    c.force_login(staff)
    return c


@pytest.fixture
def rf():
    return RequestFactory()


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


@pytest.fixture
def pj():
    return post_json


def make_request(rf, user=None, cookies=None, **extra):
    from django.contrib.auth.models import AnonymousUser

    request = rf.post("/x/", **extra)
    request.user = user or AnonymousUser()
    if cookies:
        request.COOKIES.update(cookies)
    return request


@pytest.fixture
def mkreq(rf):
    return lambda user=None, cookies=None, **extra: make_request(rf, user, cookies, **extra)


PNG = bytes.fromhex("89504e470d0a1a0a") + bytes(64)


@pytest.fixture
def png():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return lambda name="pic.png", content=PNG: SimpleUploadedFile(name, content, content_type="image/png")


@pytest.fixture
def sync_settings(settings):
    """Helper to set SUPCHAT while keeping background work synchronous."""

    def apply(**kw):
        settings.SUPCHAT = {"BACKGROUND": "sync", **kw}

    return apply
