"""Cheap exclusions before ranking and before a candidate can be approved."""
import re

_CITED_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_CITATION_MARK = re.compile(r"et al\.?|\[\d{1,3}\]|arXiv|doi\.org|doi:|\bpp\. ?\d|\bvol\. ?\d|Proceedings|preprint|\b[A-Z]\. ?(?:[A-Z]\. ?)?[A-Z][a-z]+,", re.I)
_CITATION_RUN = re.compile(r"(?:\[\d{1,3}\][\s,;]*){3,}")
_BOILERPLATE = re.compile(
    r"공공질서 및 미풍양속|영리를 목적으로 하는 광고|타인의 메일주소, 전화번호|"
    r"맨 위로|본문 바로가기|all rights reserved|cookie (?:settings|preferences)",
    re.I,
)
# Explicit exam/qualification names disambiguate e.g. OPIc IM2 from an unrelated “7 seconds”.
_EXAM_ANCHORS = tuple(re.compile(value, re.I) for value in (
    r"오픽|\bopic\b",
    r"정보처리\s*기사|engineer information processing",
    r"정보처리\s*산업기사|industrial engineer information processing",
    r"편입|transfer admissions?",
    r"\btoeic\b|토익",
    r"\btoefl\b|토플",
    r"수능|대학수학능력시험|college scholastic ability test",
    r"\bsqld\b|sql\s*개발자",
    r"\badsp\b|데이터\s*분석\s*준전문가",
))


def looks_like_reference_list(text: str) -> bool:
    years, marks = len(_CITED_YEAR.findall(text)), len(_CITATION_MARK.findall(text))
    return bool(
        (years >= 2 and marks >= 4 and (years + marks) * 34 >= len(text))
        or (len(_CITATION_RUN.findall(text)) >= 2 and not re.search(r"[.!?](?:\s|$)", text))
        or (marks >= 3 and re.search(r"Proceedings of|Association for Computational Linguistics", text, re.I)
            and re.search(r"\b10\.\d{4,9}/|\bpages \d", text, re.I))
    )


def is_evidence_noise(text: str) -> bool:
    return bool(_BOILERPLATE.search(text) or looks_like_reference_list(text))


def is_topic_candidate(query: str, title: str, quote: str) -> bool:
    if is_evidence_noise(quote):
        return False
    anchors = [anchor for anchor in _EXAM_ANCHORS if anchor.search(query)]
    return not anchors or any(anchor.search(title) or anchor.search(quote) for anchor in anchors)
