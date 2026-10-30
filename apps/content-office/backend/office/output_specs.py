"""Versioned blog output contract; existing saved drafts remain readable."""
def output_issues(packet):
    if 'titles' not in packet and 'hashtags' not in packet:
        return []
    issues=[]
    if not 1350 <= len(packet.get('body','')) <= 1650: issues.append('블로그 본문은 1,500자±10%여야 합니다')
    for key,count in [('titles',3),('hashtags',5)]:
        values=packet.get(key,[])
        if not isinstance(values,list) or len(values)!=count or any(not isinstance(v,str) or not v.strip() for v in values) or len(set(values))!=count: issues.append(f'{key}는 서로 다른 {count}개가 필요합니다')
    if any(not v.startswith('#') or any(c.isspace() for c in v) for v in packet.get('hashtags',[]) if isinstance(v,str)): issues.append('해시태그는 #으로 시작하고 공백을 포함하지 않아야 합니다')
    return issues
