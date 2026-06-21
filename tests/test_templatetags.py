import pytest
from django.template import Context, Template
from django.test import RequestFactory

pytestmark = pytest.mark.django_db


def test_supchat_template_tag_renders_widget():
    request = RequestFactory().get("/")
    rendered = Template("{% load supchat %}{% supchat title='Help' position='left' %}").render(Context({"request": request}))
    assert "data-supchat" in rendered
    assert "Help" in rendered
    assert "supchat-left" in rendered
