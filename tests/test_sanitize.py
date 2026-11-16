import pytest
from django.core.exceptions import ValidationError

from supchat.services import sanitize_message_text as san


def test_strips_html():
    assert san("<script>alert(1)</script>hi <b>there</b>") == "alert(1)hi there"


def test_strips_control_chars():
    assert san("a\x00b\x07c\x7f") == "abc"


def test_normalizes_newlines_and_strips():
    assert san("  a\r\nb\rc  ") == "a\nb\nc"


def test_keeps_unicode():
    assert san("سلام 👋") == "سلام 👋"


@pytest.mark.parametrize("bad", ["", "   ", "<b></b>", "\x00"])
def test_empty_rejected(bad):
    with pytest.raises(ValidationError):
        san(bad)


def test_non_string_rejected():
    with pytest.raises(ValidationError):
        san(123)


def test_max_length(settings):
    settings.SUPCHAT = {"MAX_MESSAGE_LENGTH": 5}
    assert san("12345") == "12345"
    with pytest.raises(ValidationError):
        san("123456")
