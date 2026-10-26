from jobalert.text import contains_token, match_forms, normalize_loose, split_sections, strip_html


def test_strip_html_removes_tags_and_entities():
    assert strip_html("<p>요구사항&nbsp;정의</p>").split() == ["요구사항", "정의"]


def test_normalize_loose_splits_punctuation():
    assert normalize_loose("UX/UI 개선") == "ux ui 개선"


def test_padded_alias_requires_word_boundary():
    assert contains_token(match_forms("GA 를 활용한 분석"), " ga ")
    assert not contains_token(match_forms("가격 정책 관리"), " ga ")


def test_alias_with_slash_matches():
    assert contains_token(match_forms("A/B 테스트 설계"), "a/b 테스트")


def test_split_sections_detects_korean_headers():
    text = """주요 업무
- 서비스 기획
자격요건
- 요구사항 정의 경험
우대사항
- SQL 활용 가능
혜택 및 복지
- 연차
"""
    sections = split_sections(text)
    assert "요구사항 정의 경험" in sections["requirements"]
    assert "SQL 활용 가능" in sections["preferred"]
    assert "서비스 기획" in sections["main_tasks"]
    assert "연차" in sections["benefits"]


def test_split_sections_handles_alternative_headers():
    text = """이런 분을 찾아요
- 화면설계서 작성 경험
이런 경험이 있다면 더 좋아요
- 애자일 경험
"""
    sections = split_sections(text)
    assert "화면설계서" in sections["requirements"]
    assert "애자일" in sections["preferred"]
