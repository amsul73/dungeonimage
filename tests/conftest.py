from pathlib import Path

import pytest

from jobalert.config import DEFAULT_KEYWORDS, Profile

TEST_PROFILE = Path(__file__).parent / "fixtures" / "test_profile.yaml"


@pytest.fixture()
def profile() -> Profile:
    """고정된 테스트용 프로필. 실제 profile.yaml 수정과 무관하게 동작한다."""
    return Profile.load(TEST_PROFILE, DEFAULT_KEYWORDS)
