"""출고 승인된 여러 원고를 같은 회차의 이메일·Slack·웹 초안으로 만든다."""
from __future__ import annotations

from html import escape
import re
from urllib.parse import urlsplit

from .exports import blog_markdown, plain_text
from .newsletter_distribution import DESTINATIONS, connection_contract
from .store import WorkflowError

KINDS = {'briefing': 'AI 빠른 소식', 'analysis': 'AI 심층 큐레이션', 'updates': 'HeoBrain 상품·서비스 소식'}


def normalize_editorial(value, primary_id):
    if not isinstance(value, dict) or value.get('kind') not in KINDS:
        raise WorkflowError('회차 목적을 선택하세요')
    related, destinations = value.get('related_job_ids', []), value.get('destinations', [])
    if (not isinstance(related, list) or len(related) > 7 or any(not isinstance(x, str) or not x.strip() or len(x) > 100 for x in related)
            or len(set(related)) != len(related) or primary_id in related):
        raise WorkflowError('서로 다른 출고 작업을 대표 작업 포함 최대 8개까지 선택하세요')
    if (not isinstance(destinations, list) or not destinations or any(not isinstance(x, str) or x not in DESTINATIONS for x in destinations)
            or len(set(destinations)) != len(destinations)):
        raise WorkflowError('전달 목적지를 하나 이상 확인하세요')
    return {'kind': value['kind'], 'related_job_ids': related, 'destinations': sorted(destinations)}


def _source_url(job):
    url = str(job.get('article', {}).get('url') or '')
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme not in ('http', 'https') or not host or '.' not in host or parsed.username or parsed.password
                or re.search(r'PRIVATE|/api/jobs/|localhost|127\.0\.0\.1|file:', url, re.I)):
            return ''
        return url
    except ValueError:
        return ''


def package_content(store, db, job, release, subject, editorial):
    from .newsletter import _released_job
    editorial = normalize_editorial(editorial, job['id'])
    jobs = [(job, release)] + [_released_job(db, store, item) for item in editorial['related_job_ids']]
    # A newsletter cannot silently export an unapproved blog when only video was released.
    if any('blog' not in approved['outputs'] for _, approved in jobs):
        raise WorkflowError('묶을 원고마다 블로그 출고 승인②가 필요합니다')
    articles, snapshots, sources = [], [], []
    for item, approved in jobs:
        packet = item['source_packet']
        title = str(packet.get('title') or item['title'])
        body = blog_markdown(packet, item.get('offer')).strip()
        url = _source_url(item)
        articles.append({'title': title, 'markdown': body, 'url': url})
        snapshots.append({'job_id': item['id'], 'source_hash': item['source_hash'], 'release_version': approved['version']})
        sources.append({'job_id': item['id'], 'title': title, 'url': url,
                        'publisher': urlsplit(url).hostname if url else '원출처 URL 확인 필요'})
    markdown = '# ' + subject + '\n\n' + '\n\n---\n\n'.join('## ' + item['title'] + '\n\n' + item['markdown'] + ('\n\n원출처: ' + item['url'] if item['url'] else '') for item in articles)
    text = plain_text(markdown)
    parts = []
    for item in articles:
        paragraphs = ''.join('<p style="font-size:16px;line-height:1.9;word-break:keep-all;overflow-wrap:anywhere">'
                             + escape(plain_text(part)).replace('\n', '<br>') + '</p>' for part in item['markdown'].split('\n\n') if part.strip())
        source = '<p><a href="' + escape(item['url'], quote=True) + '">원출처 읽기</a></p>' if item['url'] else '<p>원출처 URL을 확인해 주세요.</p>'
        parts.append('<section><h2 style="font-size:23px;line-height:1.5;word-break:keep-all">' + escape(item['title']) + '</h2>' + paragraphs + source + '</section>')
    html = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(subject) + '</title></head><body style="margin:0;background:#f2f1e9;color:#203a35;font-family:Arial,sans-serif">'
            '<table role="presentation" width="100%"><tr><td align="center"><div style="box-sizing:border-box;max-width:640px;width:100%;padding:24px;background:#fffdf7">'
            '<p>HeoBrain · ' + KINDS[editorial['kind']] + '</p><h1 style="font-size:28px;word-break:keep-all;overflow-wrap:anywhere">'
            + escape(subject) + '</h1>' + ''.join(parts)
            + '<hr><p style="font-size:13px">검토용 패키지입니다. 수신거부·발신자·수신 대상 확인 후 별도 발송 절차가 필요합니다.</p></div></td></tr></table></body></html>')
    # Keep the full reviewed copy; do not silently truncate it into a different claim.
    slack = subject + '\n\n' + '\n\n'.join(item['title'] + '\n' + plain_text(item['markdown']) + ('\n' + item['url'] if item['url'] else '') for item in articles)
    slack = escape(slack, quote=False)
    outputs = {'email': {'html': html, 'text': text}, 'slack': {'text': slack, 'unfurl_links': False, 'unfurl_media': False},
               'website': {'title': subject, 'markdown': markdown, 'state': 'draft'}}
    return {'markdown': markdown, 'editorial': editorial, 'package': {
        'version': 1, 'article_count': len(articles), 'publisher_count': len({row['publisher'] for row in sources if row['url']}),
        'source_note': '발행사 수는 독립 검증 수가 아닙니다. 같은 사건·전재 여부와 원문은 별도로 검토하세요.',
        'sources': sources, 'snapshots': snapshots, 'connection_contract': connection_contract(editorial['destinations']),
        'outputs': {key: outputs[key] for key in editorial['destinations']}, 'external_sent': False}}
