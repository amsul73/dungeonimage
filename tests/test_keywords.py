import pytest

from jobalert.config import DEFAULT_KEYWORDS
from jobalert.keywords import KeywordDictionary


@pytest.fixture(scope="module")
def dictionary() -> KeywordDictionary:
    return KeywordDictionary.load(DEFAULT_KEYWORDS)


def test_resolve_by_alias_label_and_id(dictionary):
    assert dictionary.resolve("피그마") == "figma"
    assert dictionary.resolve("Figma") == "figma"
    assert dictionary.resolve("figma") == "figma"


def test_extract_finds_expected_keywords(dictionary):
    found = {kw.id for kw in dictionary.extract("SQL 쿼리 작성과 A/B 테스트 설계, 피그마 활용")}
    assert {"sql", "ab_test", "figma"} <= found


def test_extract_on_empty_text(dictionary):
    assert dictionary.extract("   ") == []
