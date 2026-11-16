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


def test_widget_config_json(settings):
    import html
    import json
    import re

    settings.SUPCHAT = {"TITLE": "Help", "QUICK_REPLIES": ["Hi"], "LANGUAGE": "fa", "AI": {"ENABLED": True, "API_KEY": "secret-key"}}
    out = render("{% supchat %}")
    cfg = json.loads(html.unescape(re.search(r'data-config="([^"]+)"', out).group(1)))
    assert cfg["title"] == "Help" and cfg["language"] == "fa" and cfg["quickReplies"] == ["Hi"] and cfg["ai"] is True
    assert cfg["configUrl"] == "/supchat/config/"
    assert "secret-key" not in out  # never leak provider credentials into the page


def test_language_override():
    import html

    out = html.unescape(render('{% supchat language="ar" %}'))
    assert '"language": "ar"' in out
