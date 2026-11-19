import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

from office import public_discovery as discovery
from office.public_evidence import public_evidence_id


def _check_hashes(result):
    ids = set()
    for evidence in result['references']:
        quote_hash = hashlib.sha256(evidence['quote'].encode()).hexdigest()
        assert quote_hash == evidence['quote_sha256']
        assert public_evidence_id(evidence['url'], evidence['source_sha256'], evidence['paragraph'], quote_hash) == evidence['id']
        ids.add(evidence['id'])
    assert ids == set().union(*(set(claim['evidence_ids']) for claim in result['claims']))


def test_worldcraft_direct_site_excludes_homonymous_research(monkeypatch):
    home = b'<title>WorldCraft</title><main><h1>World Craft</h1><p>A 1:1 scale replica of Earth in Minecraft</p><p>Join on Minecraft 26.2:</p></main>'
    terms = b'<title>Terms | WorldCraft</title><main><h2>Who we are</h2><p>WorldCraft is a Minecraft server that recreates real places, plus this website and store.</p></main>'
    urls = {'https://worldcraft.gg/robots.txt': b'User-agent: *\nAllow: /\n',
            'https://worldcraft.gg/': home, 'https://worldcraft.gg/terms': terms}
    seen = []

    def fetch(url, **kwargs):
        seen.append(url)
        assert kwargs.get('allowed_hosts') == {'worldcraft.gg'}
        return urls[url], url, 'text/plain' if url.endswith('robots.txt') else 'text/html'

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    result = discovery.discover_public_evidence('WorldCraft 마인크래프트 지구 구현',
        seed_urls=('https://worldcraft.gg/', 'https://arxiv.org/abs/2605.25077'))
    assert result['status'] == 'ready'
    assert [ref['url'] for ref in result['references']] == ['https://worldcraft.gg/', 'https://worldcraft.gg/terms']
    assert len(result['claims']) == 2
    assert all('Minecraft' in ref['quote'] for ref in result['references'])
    assert seen == list(urls)
    _check_hashes(result)


def _repository(name, *, owner='example', fork=False, description=None):
    return {'name': name, 'full_name': f'{owner}/{name}', 'private': False, 'fork': fork,
            'html_url': f'https://github.com/{owner}/{name}', 'description': description}


def test_github_dynamic_original_readme_excludes_forks_and_links_stored_claims(monkeypatch):
    names = {'MoneyPrinterTurbo': 'harry0703', 'NovelBuildGraph': 'novel-org'}
    quotes = {'MoneyPrinterTurbo': 'Generate the script, subtitles, and footage for a short video from a topic or keyword.',
              'NovelBuildGraph': 'Construct reusable dependency graphs by factoring shared tasks across multiple local projects.'}
    seen = []

    def fetch(url, **kwargs):
        assert kwargs.get('allowed_hosts') == {'api.github.com'}
        seen.append(url)
        parts = urlsplit(url)
        if parts.path == '/search/repositories':
            name = parse_qs(parts.query)['q'][0].split()[0]
            data = {'incomplete_results': False, 'items': [_repository(name, owner='copy', fork=True),
                     _repository(name, owner='mirror', description=f'{names[name]}/{name} mirror'),
                     _repository(name + '-mirror'), _repository(name, owner=names[name])]}
        else:
            _, _, owner, name, tail = parts.path.split('/')
            assert tail == 'readme' and owner == names[name]
            readme = f'# {name}\n\n{quotes[name]}\n\n## USAGE\n'
            data = {'type': 'file', 'encoding': 'base64', 'path': 'README.md',
                    'html_url': f'https://github.com/{owner}/{name}/blob/main/README.md',
                    'content': base64.b64encode(readme.encode()).decode()}
        return json.dumps(data).encode(), url, 'application/json'

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    for name, topic in [('MoneyPrinterTurbo', '숏폼 영상'), ('NovelBuildGraph', 'dependency graphs')]:
        result = discovery.discover_public_evidence(f'{name} {topic}', limit=1)
        assert result['status'] == 'ready'
        assert [ref['quote'] for ref in result['references']] == [quotes[name]]
        assert result['references'][0]['url'] == f'https://github.com/{names[name]}/{name}/blob/main/README.md'
        _check_hashes(result)
    assert len(seen) == 4


def test_verified_repo_link_uses_same_repo_languaged_readme_and_stable_release(monkeypatch):
    name = 'maintainer/UsefulBuildGraph'
    home = f'https://github.com/{name}'
    intro = 'Generate reusable dependency graphs across build pipelines from a declared manifest.'
    released = 'Added dependency graph caching for repeated builds across multiple workspaces.'
    bodies = {'README.md': '# UsefulBuildGraph\n\n[English](README-en.md)',
              'README-en.md': f'# UsefulBuildGraph\n\n{intro}\n[![Badge](https://example.net/badge)](https://example.net)'}

    def fetch(url, **kwargs):
        assert kwargs['deadline'] > discovery.monotonic()
        path = urlsplit(url).path
        if path == f'/repos/{name}':
            data = _repository('UsefulBuildGraph', owner='maintainer')
        elif path.endswith('/releases/latest'):
            data = {'tag_name': 'v1.2.0', 'draft': False, 'prerelease': False, 'body': f'## Changes\n\n- {released}',
                    'published_at': '2026-11-18T18:11:00Z', 'html_url': home + '/releases/tag/v1.2.0'}
        else:
            filename = 'README.md' if path.endswith('/readme') else path.split('/')[-1]
            data = {'type': 'file', 'encoding': 'base64', 'path': filename, 'html_url': f'{home}/blob/main/{filename}',
                    'content': base64.b64encode(bodies[filename].encode()).decode()}
        return json.dumps(data).encode(), url, 'application/json'

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    result = discovery.discover_public_evidence('공용 빌드 의존성 그래프', seed_urls=(home,))
    assert result['status'] == 'ready'
    assert [ref['quote'] for ref in result['references']] == [intro, released]
    assert [ref['url'] for ref in result['references']] == [home + '/blob/main/README-en.md', home + '/releases/tag/v1.2.0']
    _check_hashes(result)


def test_ambiguous_and_unsupported_results_do_not_fetch_untrusted_urls(monkeypatch):
    seen = []

    def fetch(url, **kwargs):
        seen.append(url)
        assert urlsplit(url).netloc == 'api.github.com'
        data = {'incomplete_results': False, 'items': [_repository('NovaBridge'),
                _repository('NovaBridge', owner='other')]}
        return json.dumps(data).encode(), url, 'application/json'

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    result = discovery.discover_public_evidence('NovaBridge 기능', seed_urls=('https://127.0.0.1/secret',
        'https://example.com/unregistered', 'https://user:pass@github.com/name/NovaBridge'))
    assert result == {'status': 'insufficient', 'claims': [], 'references': []}
    assert len(seen) == 1


def test_robot_denial_yields_no_website_evidence(monkeypatch):
    def fetch(url, **kwargs):
        assert url == 'https://worldcraft.gg/robots.txt'
        return b'User-agent: *\nDisallow: /\n', url, 'text/plain'

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    result = discovery.discover_public_evidence('WorldCraft Minecraft', seed_urls=('https://worldcraft.gg/',))
    assert result == {'status': 'insufficient', 'claims': [], 'references': []}


def test_local_index_reuse_cannot_include_unanchored_domains(monkeypatch):
    url = 'https://deepmind.google/blog/safe-agent-evals'
    quote = 'The research evaluates AI agents on structured dependency graphs with controlled baselines.'
    sha = hashlib.sha256(quote.encode()).hexdigest()
    indexed = {'id': public_evidence_id(url, sha, 3, sha), 'url': url, 'title': 'Safe agent evals',
               'paragraph': 3, 'quote': quote, 'source_sha256': sha, 'quote_sha256': sha}

    def fetch(url, **kwargs):
        raise OSError('offline')

    def search(title, **kwargs):
        return [{**indexed, 'url': 'https://outside.example/agent-evals'}, indexed]

    monkeypatch.setattr(discovery, 'fetch_public', fetch)
    monkeypatch.setattr(discovery, 'find_public_evidence', search)
    result = discovery.discover_public_evidence('agent dependency graphs', seed_urls=(url,))
    assert result['references'] == [indexed]
    _check_hashes(result)
