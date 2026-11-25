"""Find candidate evidence in official public pages and public GitHub documentation."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from itertools import islice
from threading import BoundedSemaphore
from time import monotonic
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

from .evidence import extract_article_text, extract_page_text
from .feeds import DEFAULT_FEEDS, fetch_public, parse_date
from .public_evidence import PublicEvidenceUnavailable, find_public_evidence, public_evidence_id


_GITHUB_API = 'https://api.github.com'
_WORLDCRAFT = 'worldcraft.gg'
_EXCLUDED_FEEDS = {'hacker-news', 'arxiv-cs-ai', 'google-news', 'google-trends', 'youtube-google', 'youtube-openai'}
_OFFICIAL_HOSTS = frozenset({urlsplit(feed['url']).hostname for feed in DEFAULT_FEEDS
                             if feed['id'] not in _EXCLUDED_FEEDS} | {_WORLDCRAFT, 'arxiv.org'})
_SAFE_REPO = re.compile(r'([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9][A-Za-z0-9_.-]{0,99})\Z')
_ENGLISH = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9._-]{2,63}(?![A-Za-z0-9_])')
_SOCIAL_CLUTTER = re.compile(r'\b(sponsors?|sponsored|sponsorship|advertisement|privacy policy|sign in|cookie preferences|all rights reserved)\b', re.I)
_README_NAME = re.compile(r'README(?:[-_.][A-Za-z0-9]+)*\Z', re.I)
_README_ENGLISH = re.compile(r'\[English\]\((README[-_.]en(?:\.[A-Za-z0-9]+)?)\)', re.I)
_PROMOTION_HEADING = re.compile(r'(thanks|sponsor|partner|advertis|赞助|感谢|贊助|優惠|후원|협찬)', re.I)
_DERIVATIVE_REPOSITORY = re.compile(r'\b(?:mirror|fork|repack|unofficial)\b|\bdocker (?:image|container) for\b', re.I)
_GENERIC = frozenset({'the', 'and', 'how', 'can', 'new', 'what', 'this', 'with', 'features', 'feature', 'function',
                      'project', 'tool', 'using', 'for', 'use', 'open', 'source', 'overview', 'review', 'documentation',
                      'release', 'guide', 'does', 'from', 'who', 'official', 'beta', 'latest', 'github'})
_KOREAN_TERMS = {
    '숏폼': {'shorts', 'short', 'reels'}, '쇼츠': {'shorts', 'short', 'reels'}, '영상': {'video', 'videos'},
    '자막': {'subtitle', 'subtitles', 'captions'}, '대본': {'script', 'scripts'}, '음성': {'voice', 'tts', 'speech'},
    '자동화': {'automation', 'automated', 'automate'}, '라이선스': {'license', 'licensed'},
    '요금': {'price', 'pricing', 'cost', 'plan'}, '비용': {'price', 'pricing', 'cost'},
    '설치': {'install', 'installation', 'setup'}, '의존성': {'dependencies', 'dependency'},
    '그래프': {'graph', 'graphs'}, '검색': {'search', 'retrieval'},
    '마인크래프트': {'minecraft'}, '오픈소스': {'license', 'licensed', 'open-source'},
    '음성인식': {'asr', 'speech', 'recognition'}, '화자': {'speaker', 'diarization'},
    '타임스탬프': {'timestamp', 'timestamps'}, '전사': {'transcribe', 'transcription'},
    '정제': {'cleaning', 'cleanup', 'clean', 'messy'}, '데이터': {'data', 'dataset'},
}
_SECONDS = 12
_MAX_BYTES = 750_000
_MAX_FETCHES = 6
_WORKERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='public-originals')
_SLOTS = BoundedSemaphore(2)


def _parts(url):
    if not isinstance(url, str) or len(url) > 1500 or re.search(r'[\x00-\x20\\%]', url):
        return None
    try:
        parts = urlsplit(url)
        if (parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password
                and parts.port in (None, 443) and not parts.query):
            return parts
    except ValueError:
        pass
    return None


def _key(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def _words(value):
    return {word.casefold().strip('._-') for word in _ENGLISH.findall(value)} - _GENERIC


def _focus(value, entity):
    words = _words(re.sub(r'https?://\S+', '', value)) - {entity.casefold()}
    for cue, alternatives in _KOREAN_TERMS.items():
        if cue in value:
            words.update(alternatives)
    return words


def _contains(name, value):
    folded = r'[-_. ]*'.join(re.escape(part) for part in re.split(r'[-_. ]+', name.strip()))
    return bool(re.search(rf'(?<![a-z0-9]){folded}(?![a-z0-9])', value, re.I))


def _entity(title):
    words = [word.strip('._-') for word in _ENGLISH.findall(title) if word.casefold().strip('._-') not in _GENERIC]
    for word in words:
        if re.search(r'[a-z0-9][A-Z]|[a-zA-Z][-_.][a-zA-Z0-9]|[a-zA-Z][0-9]', word):
            return word
    return ''


def _result(references=(), claims=(), *, reason=None):
    if reason:
        return {'status': 'unavailable', 'reason': reason, 'claims': [], 'references': []}
    return {'status': 'ready' if references else 'insufficient', 'claims': list(claims),
            'references': list(references)}


def _reference(url, title, paragraph, quote, raw):
    quote = quote.strip()
    if len(quote) > 240:
        quote = re.sub(r'\s+\S*\Z', '', quote[:240]).rstrip() or quote[:240]
    source_hash = hashlib.sha256(raw).hexdigest()
    quote_hash = hashlib.sha256(quote.encode('utf-8')).hexdigest()
    return {'id': public_evidence_id(url, source_hash, paragraph, quote_hash), 'url': url, 'title': title[:500],
            'paragraph': paragraph, 'quote': quote, 'source_sha256': source_hash, 'quote_sha256': quote_hash}


def _plain(value):
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def _paragraphs(text):
    return [(number, ' '.join(part.split()))
            for number, part in enumerate(re.split(r'\n\s*\n', text), 1) if part.strip()]


def _pick(paragraphs, terms, *, identity=False):
    candidates = []
    for number, quote in paragraphs:
        if len(quote) < 35 or _SOCIAL_CLUTTER.search(quote):
            continue
        topical = _focus(quote, '') & terms
        if not identity and not topical:
            continue
        if terms and not topical:
            continue
        candidates.append((len(topical), -number, quote))
    if candidates:
        _, position, quote = max(candidates)
        return -position, quote
    return None


class _Lookup:
    def __init__(self, deadline):
        self.deadline = deadline
        self.remaining = _MAX_FETCHES
        self.robots = {}

    def fetch(self, url, host, maximum=_MAX_BYTES):
        if self.remaining <= 0 or monotonic() >= self.deadline:
            return None
        self.remaining -= 1
        raw, resolved, content_type = fetch_public(url, maximum=maximum, allowed_hosts={host}, deadline=self.deadline)
        parts = urlsplit(resolved)
        if (parts.scheme != 'https' or parts.hostname != host or parts.username or parts.password
                or parts.port not in (None, 443) or monotonic() >= self.deadline):
            return None
        return raw, resolved, content_type.lower()

    def json(self, path):
        try:
            response = self.fetch(_GITHUB_API + path, 'api.github.com')
            if response and ('application/json' in response[2] or '+json' in response[2]):
                obj = json.loads(response[0])
                return obj if isinstance(obj, dict) else {}
        except (requests.RequestException, OSError, ValueError):
            pass
        return {}

    def _is_allowed(self, url):
        parts = urlsplit(url)
        if parts.hostname not in self.robots:
            robots_url = 'https://' + parts.hostname + '/robots.txt'
            robot = RobotFileParser(robots_url)
            try:
                response = self.fetch(robots_url, parts.hostname, maximum=32_000)
                if response and response[1] == robots_url and 'text/plain' in response[2]:
                    robot.parse(response[0].decode('utf-8-sig').splitlines())
                elif response and response[1] == robots_url and not response[0].strip():
                    robot.parse([])
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code in (404, 410):
                    robot.parse([])
            except (requests.RequestException, OSError, ValueError):
                pass
            self.robots[parts.hostname] = robot
        return self.robots[parts.hostname].can_fetch('HeoBrainContentOffice', url)

    def html(self, url):
        if not self._is_allowed(url):
            return None
        try:
            response = self.fetch(url, urlsplit(url).hostname)
            if response and response[1] == url and ('text/html' in response[2] or 'application/xhtml+xml' in response[2]):
                return response[0], response[0].decode('utf-8')
        except (requests.RequestException, OSError, ValueError):
            pass
        return None


def _worldcraft(lookup):
    facts = (
        ('/', 'WorldCraft · 서비스 소개', '지구 구현 범위', r'\b1\s*:\s*1\b[^.!?]*\bEarth\b[^.!?]*\bMinecraft\b'),
        ('/terms', 'WorldCraft · 이용약관', '운영 주체가 설명한 서비스 유형',
         r'\bWorld\s*Craft\s+is\s+a\s+Minecraft\s+server\b[^.!?]*\brecreates real places\b'),
    )
    hits = []
    for path, name, label, pattern in facts:
        url = f'https://{_WORLDCRAFT}{path}'
        response = lookup.html(url)
        if response:
            raw, markup = response
            for number, quote in _paragraphs(extract_article_text(markup)):
                if re.search(pattern, quote, re.I):
                    hits.append((label, _reference(url, name, number, quote, raw)))
                    break
    return hits


def _repo_name(record):
    if not isinstance(record, dict) or record.get('private') is not False or record.get('fork') is not False:
        return ''
    full_name = record.get('full_name')
    if (isinstance(full_name, str) and _SAFE_REPO.fullmatch(full_name)
            and record.get('html_url') == f'https://github.com/{full_name}'
            and record.get('name') == full_name.split('/')[1]):
        return full_name
    return ''


def _github_repository(lookup, seeds, entity, terms):
    for seed in seeds:
        full_name = '/'.join(seed.path.strip('/').split('/')[:2])
        if seed.hostname == 'github.com' and _SAFE_REPO.fullmatch(full_name):
            if entity and _key(entity) != _key(full_name.split('/')[1]):
                continue
            validated = _repo_name(lookup.json(f'/repos/{full_name}'))
            if validated.casefold() == full_name.casefold():
                return validated, True
    if not entity or len(entity) < 4 or _key(entity) in ('worldcraft', 'localhost') or not re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]{3,63}', entity):
        return '', False
    params = urlencode({'q': f'{entity} in:name fork:false', 'per_page': 12})
    data = lookup.json(f'/search/repositories?{params}')
    if data.get('incomplete_results') is not False or not isinstance(data.get('items'), list):
        return '', False
    matches = {}
    for row in data['items']:
        name = _repo_name(row)
        if name and _key(name.split('/')[1]) == _key(entity):
            description = row.get('description') or ''
            if isinstance(description, str) and not _DERIVATIVE_REPOSITORY.search(description):
                matches[name] = description
    if len(matches) > 1 and terms:
        matches = {name: description for name, description in matches.items() if _focus(description, entity) & terms}
    return (next(iter(matches)), False) if len(matches) == 1 else ('', False)


def _readme(data, name):
    url = data.get('html_url')
    parts = _parts(url)
    path = parts.path.split('/') if parts else []
    filename = data.get('path')
    if (not parts or parts.hostname != 'github.com' or len(path) < 6 or '/'.join(path[1:3]).casefold() != name.casefold()
            or path[3] != 'blob' or data.get('type') != 'file' or data.get('encoding') != 'base64'
            or not isinstance(filename, str) or not _README_NAME.fullmatch(filename) or path[-1] != filename):
        return None
    try:
        raw = base64.b64decode(''.join(data['content'].split()), validate=True)
        text = raw.decode('utf-8-sig')
    except (AttributeError, KeyError, UnicodeError, ValueError):
        return None
    return url, raw, text


def _readme_rows(text):
    promotion = False
    fenced = False
    for number, block in enumerate(re.split(r'\n\s*\n', text), 1):
        for line in block.splitlines():
            line = line.lstrip()
            if line.startswith(('```', '~~~')):
                fenced = not fenced
            if fenced or not line or line.startswith(('`', '<', '[!', '![', '|', '---', '>')):
                continue
            if line.startswith('#'):
                promotion = bool(_PROMOTION_HEADING.search(line))
                continue
            if not promotion and not _README_ENGLISH.search(line) and not _SOCIAL_CLUTTER.search(line):
                line = re.sub(r'^\s*[-*+]\s+(?:\[[xX ]\]\s*)?', '', line)
                line = re.sub(r'\[([^]\n]+)\]\(https?://[^)]+\)', r'\1', line)
                quote = _plain(line)
                if quote:
                    yield number, quote


def _release(lookup, name, terms):
    data = lookup.json(f'/repos/{name}/releases/latest')
    tag = data.get('tag_name')
    title = data.get('name') or tag
    body = data.get('body')
    if (data.get('draft') is not False or data.get('prerelease') is not False
            or not isinstance(tag, str) or not re.fullmatch(r'[0-9A-Za-z._-]{1,80}', tag)
            or not isinstance(title, str) or not isinstance(body, str)
            or not isinstance(data.get('published_at'), str) or not parse_date(data['published_at'])):
        return None
    url = f'https://github.com/{name}/releases/tag/{tag}'
    if data.get('html_url') != url:
        return None
    best = _pick(_readme_rows(body), terms, identity=True)
    if best:
        number, quote = best
        return '최근 정식 릴리스의 변경 내용', _reference(url, f'{name} · {title}', number, quote, body.encode())
    return None


def _github(lookup, title, seeds, entity, context, limit):
    terms = _focus(title, entity) or _focus(context, entity)
    name, anchored = _github_repository(lookup, seeds, entity, terms)
    if not name:
        return []
    terms = _focus(title, entity or name.split('/')[1]) or _focus(context, entity or name.split('/')[1])
    if not anchored and not terms:
        return []
    document = _readme(lookup.json(f'/repos/{name}/readme'), name)
    if not document:
        return []
    url, raw, text = document
    linked_english = _README_ENGLISH.search(text[:6000])
    if linked_english:
        alternative = _readme(lookup.json(f'/repos/{name}/contents/{linked_english[1]}'), name)
        if alternative:
            url, raw, text = alternative
    rows = _readme_rows(text)
    best = _pick(rows, terms, identity=anchored)
    if best:
        number, quote = best
        scope = '공식 저장소 README의 기능 설명' if anchored else '이름이 일치한 공개 저장소 · 확인 필요'
        hits = [(scope, _reference(url, f'{name} · README', number, quote, raw))]
        if limit > 1 and (release := _release(lookup, name, terms)):
            if not anchored:
                release = ('이름이 일치한 공개 저장소의 릴리스 · 확인 필요', release[1])
            hits.append(release)
        return hits
    return []


def _official_url(title, seed, entity):
    if seed.hostname == 'arxiv.org':
        if not re.fullmatch(r'/abs/[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?', seed.path):
            return None
        if _key(entity) == 'worldcraft' and not re.search(r'paper|study|논문|연구|trajectory|photorealistic', title, re.I):
            return None
    if seed.hostname not in _OFFICIAL_HOSTS or seed.hostname == _WORLDCRAFT or seed.path in ('', '/'):
        return None
    return urlunsplit(('https', seed.hostname, seed.path, '', ''))


def _official_article(lookup, title, seed, entity):
    url = _official_url(title, seed, entity)
    if not url:
        return None
    response = lookup.html(url)
    if not response:
        return None
    raw, markup = response
    title_match = re.search(r'<title(?:\s[^>]*)?>(.*?)</title\s*>', markup, re.I | re.S)
    original_title = _plain(title_match[1]) if title_match else ''
    if not original_title or (entity and not _contains(entity, original_title)):
        return None
    # arXiv 초록 페이지는 'Abstract:' 문단 규칙이 예전 파서 기준이라 그대로 둔다. 나머지는 구조 추출(2026-11-25).
    rows = _paragraphs(extract_article_text(markup) if seed.hostname == 'arxiv.org' else extract_page_text(markup, url)[0])
    if seed.hostname == 'arxiv.org':
        rows = [(number, re.sub(r'^Abstract:\s*', '', quote, flags=re.I)) for number, quote in rows
                if quote.lower().startswith('abstract:')]
    else:
        rows = [(number, quote) for number, quote in rows if quote != original_title]
    best = _pick(rows, _focus(title, entity), identity=bool(entity))
    if best:
        number, quote = best
        return '공개 원문 본문', _reference(url, original_title, number, quote, raw)
    return None


def _indexed_hits(title, seeds, entity, used):
    scoped = {url for seed in seeds if (url := _official_url(title, seed, entity)) and url not in used}
    if not scoped:
        return []
    try:
        matches = find_public_evidence(title, limit=6)
    except PublicEvidenceUnavailable:
        return []
    terms = _focus(title, entity)
    return [('검토된 로컬 색인의 원문 문단', match) for match in matches if match['url'] in scoped
            and (not entity or _contains(entity, match['title']))
            and _pick([(match['paragraph'], match['quote'])], terms, identity=bool(entity))]


def _discover(title, seeds, context, limit, deadline):
    lookup = _Lookup(deadline)
    entity = _entity(title)
    worldcraft_seed = any(seed.hostname == _WORLDCRAFT and seed.path in ('', '/', '/terms') for seed in seeds)
    minecraft_title = re.search(r'minecraft|마인크래프트', title, re.I)
    worldcraft_name = re.search(r'\bworld\s*craft\b', f'{title} {context}', re.I)
    hits = []
    if worldcraft_seed or (worldcraft_name and minecraft_title):
        hits = _worldcraft(lookup)
    else:
        for seed in seeds:
            hit = _official_article(lookup, title, seed, entity)
            if hit:
                hits.append(hit)
            if len(hits) >= limit:
                break
        # A bare WorldCraft name does not identify a specific repository or paper.
        if len(hits) < limit and not worldcraft_name:
            hits.extend(_github(lookup, title, seeds, entity, context, limit - len(hits)))
        if not hits and monotonic() < deadline:
            hits.extend(_indexed_hits(title, seeds, entity, {evidence['url'] for _, evidence in hits}))
    references, claims, used = [], [], set()
    for label, evidence in hits:
        if evidence['url'] not in used and len(references) < limit:
            references.append(evidence)
            claims.append({'label': label, 'evidence_ids': [evidence['id']]})
            used.add(evidence['url'])
    return _result(references, claims)


def discover_public_evidence(title: str, *, seed_urls=(), context: str = '', limit=4) -> dict:
    """Look up a public topic without tokens, LLM calls or changes to any local state."""
    title, context = title.strip()[:320], context[:800]
    if not title or limit < 1:
        return _result()
    seeds = tuple(parts for url in islice(seed_urls, 8) if (parts := _parts(url)))
    if not _SLOTS.acquire(blocking=False):
        return _result(reason='busy')
    try:
        wait = _WORKERS.submit(_discover, title, seeds, context, min(4, limit), monotonic() + _SECONDS)
    except RuntimeError:
        _SLOTS.release()
        return _result(reason='busy')
    wait.add_done_callback(lambda _: _SLOTS.release())
    try:
        return wait.result(timeout=_SECONDS)
    except TimeoutError:
        return _result(reason='timeout')
