import pytest
from django.template import Context, Template
from django.test import RequestFactory


def render(src, **ctx):
    request = RequestFactory().get("/")
    return Template("{% load supchat %}" + src).render(Context({"request": request, **ctx}))


def test_widget_renders():
    html = render("{% supchat %}")
    assert "/supchat/start/" in html
    assert "Support" in html


def test_overrides():
    assert "Help Desk" in render('{% supchat title="Help Desk" position="left" theme="dark" %}')


def test_invalid_overrides_ignored():
    assert "/supchat/start/" in render('{% supchat position="top" theme="neon" %}')


def test_settings_title(settings):
    settings.SUPCHAT = {"TITLE": "Custom Title"}
    assert "Custom Title" in render("{% supchat %}")


def test_title_is_escaped():
    assert "<script>x</script>" not in render("{% supchat title=t %}", t="<script>x</script>")


def test_missing_urls_raises(settings):
    settings.ROOT_URLCONF = "tests.empty_urls"
    with pytest.raises(RuntimeError):
        render("{% supchat %}")
