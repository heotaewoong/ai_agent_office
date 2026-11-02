"""Free, read-only structure checks. They never judge factual quality or approve a job."""
import re
from .channel_adaptation import CHANNEL_COPY
from .editorial import cited_evidence_ids


def _text(value):
    return value if isinstance(value,str) else ''


def _without_code(body):
    lines=[];fence=None
    for line in body.splitlines():
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line)
        if marker:
            if fence is None:fence=(marker[1][0],len(marker[1]))
            elif marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip():fence=None
            continue
        if fence is None:lines.append(line)
    return '\n'.join(lines)


def analyse_packet(packet):
    title=_text(packet.get('title')).strip();body=_without_code(_text(packet.get('body')))
    paragraphs=[p.strip() for p in re.split(r'\n\s*\n',body) if p.strip() and not p.lstrip().startswith('#')]
    headings=re.findall(r'(?m)^ {0,3}#{2,3}\s+\S.*$',body)
    first=paragraphs[0] if paragraphs else '';long=sum(len(p)>350 for p in paragraphs)
    cited=cited_evidence_ids(body)
    evidence=packet.get('evidence')
    known={e['id'] for e in (evidence if isinstance(evidence,list) else []) if isinstance(e,dict) and isinstance(e.get('id'),str)}
    missing=sorted(cited-known)
    def check(key,label,passed,detail):return {'id':key,'label':label,'passed':bool(passed),'detail':detail}
    blog=[
        check('title_length','제목 길이(15~45자)',15<=len(title)<=45,f'{len(title)}자'),
        check('body_length','본문 길이(1,200자 이상)',len(body.strip())>=1200,f'{len(body.strip())}자'),
        check('headings','소제목 수(3~8개)',3<=len(headings)<=8,f'{len(headings)}개'),
        check('intro_length','첫 설명 문단 길이(160자 이하)',0<len(first)<=160,f'{len(first)}자'),
        check('short_paragraphs','긴 문단(350자 초과) 없음',bool(paragraphs) and long==0,f'{long}개'),
        check('structured','목록 또는 표 표기',bool(re.search(r'(?m)^\s*(?:[-*]|\d+\.)\s+\S|^\|.+\|$',body)),'코드 블록 제외'),
        check('citations','인용 ID가 등록 근거에 연결됨',bool(cited) and not missing,'미등록: '+', '.join(missing) if missing else ', '.join(sorted(cited)) or '인용 ID 없음'),
    ]
    posts=packet.get('channel_posts');social={}
    for key,value in (posts.items() if isinstance(posts,dict) else []):
        if key not in CHANNEL_COPY:continue
        text=_text(value).strip();limit=CHANNEL_COPY[key][0];lines=[s for s in text.splitlines() if s.strip()]
        social[key]=[
            check('length',f'채널 글자 수({limit}자 이내)',0<len(text)<=limit,f'{len(text)}자'),
            check('scannable','줄바꿈으로 구분',bool(text) and len(lines)>=3,f'{len(lines)}줄'),
            check('hashtags','해시태그 5개 이하',bool(text) and len(re.findall(r'(?<!\w)#[\w가-힣]+',text))<=5,'표기 수만 확인'),
        ]
    return {'blog':blog,'social':social,'note':'저장된 원고의 기계적 구성 정보입니다. 사실 정확성·답변 적합성·검색 순위·성과를 판정하지 않습니다. 모든 조건을 채울 필요는 없으며 원고·승인·제작을 바꾸지 않습니다.'}
