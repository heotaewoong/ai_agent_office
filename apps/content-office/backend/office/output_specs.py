"""Versioned blog output contract; existing saved drafts remain readable."""
# 글 유형별 블로그 본문 길이(공백 포함). 유형이 없으면 예전 기준 1,500자±10%예요(2026-11-27 사용자 결정).
BODY_LENGTH = {"W1": (1350, 2000), "W2": (900, 1400), "W3": (1350, 2000)}
DEFAULT_BODY_LENGTH = (1350, 1650)


def body_range(w_type=None):
    return BODY_LENGTH.get(w_type or "", DEFAULT_BODY_LENGTH)


def output_issues(packet):
    from .channel_adaptation import adaptation_issues
    issues = adaptation_issues(packet)
    if 'titles' not in packet and 'hashtags' not in packet:
        return issues
    preserve_original = packet.get('preserve_original') is True
    lo, hi = body_range(packet.get('w_type'))
    if not preserve_original and not lo <= len(packet.get('body','')) <= hi: issues.append('블로그 본문은 1,500자±10%여야 합니다' if (lo, hi) == DEFAULT_BODY_LENGTH else f'블로그 본문은 {lo:,}~{hi:,}자여야 합니다')
    for key,count in [('titles',3),('hashtags',5)]:
        if preserve_original and key not in packet:
            continue
        values=packet.get(key,[])
        if not isinstance(values,list) or len(values)!=count or any(not isinstance(v,str) or not v.strip() for v in values) or len(set(values))!=count: issues.append(f'{key}는 서로 다른 {count}개가 필요합니다')
    hashtags = packet.get('hashtags', [])
    if isinstance(hashtags, list) and any(not v.startswith('#') or any(c.isspace() for c in v) for v in hashtags if isinstance(v,str)): issues.append('해시태그는 #으로 시작하고 공백을 포함하지 않아야 합니다')
    return issues
