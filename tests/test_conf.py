import pytest

from supchat.conf import DEFAULTS, supchat_settings


def test_defaults_applied():
    assert supchat_settings.get("TITLE") == DEFAULTS["TITLE"]
    assert supchat_settings.get("MAX_MESSAGE_LENGTH") == 2000


def test_override(settings):
    settings.SUPCHAT = {"TITLE": "Help"}
    assert supchat_settings.get("TITLE") == "Help"
    assert supchat_settings.get("POSITION") == "right"


@pytest.mark.parametrize(
    "bad",
    [{"POSITION": "top"}, {"THEME": "neon"}, {"MAX_MESSAGE_LENGTH": 0}],
)
def test_invalid_values(settings, bad):
    settings.SUPCHAT = bad
    with pytest.raises(ValueError):
        supchat_settings.as_dict()


def test_non_dict_rejected(settings):
    settings.SUPCHAT = "nope"
    with pytest.raises(TypeError):
        supchat_settings.as_dict()
