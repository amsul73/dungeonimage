import pytest

from jobalert.config import DEFAULT_KEYWORDS, DEFAULT_PROFILE, Profile


@pytest.fixture()
def profile() -> Profile:
    return Profile.load(DEFAULT_PROFILE, DEFAULT_KEYWORDS)
