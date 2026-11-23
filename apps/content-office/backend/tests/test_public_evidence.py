import hashlib
import io
import json
import sqlite3
import struct
import sys
from contextlib import closing
from types import SimpleNamespace

import pytest

from office import public_evidence


MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
DIMENSIONS = 384


def vector_blob(similarity: float) -> bytes:
    return struct.pack('<384f', similarity, (1 - similarity ** 2) ** 0.5, *([0] * 382))


def build_index(tmp_path, monkeypatch, rows=(), *, model=MODEL):
    root = tmp_path / 'public-rag'
    root.mkdir()
    index = root / 'index.sqlite3'
    with closing(sqlite3.connect(index)) as db:
        db.execute('CREATE TABLE public_index_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.executemany('INSERT INTO public_index_meta VALUES (?, ?)', (
            ('schema_version', '1'), ('embedding_model', model),
            ('embedding_dimensions', str(DIMENSIONS)), ('corpus_sha256', 'a' * 64),
        ))
        db.execute('CREATE TABLE public_passages(id INTEGER PRIMARY KEY, url TEXT, title TEXT, '
                   'paragraph INTEGER, quote TEXT, source_sha256 TEXT, vector BLOB)')
        db.executemany('INSERT INTO public_passages VALUES (?, ?, ?, ?, ?, ?, ?)',
                       [(i, url, f'공개 기사 {i}', paragraph, quote, 'b' * 64, vector_blob(score))
                        for i, (url, paragraph, quote, score) in enumerate(rows, 1)])
        db.commit()
    monkeypatch.setenv('OFFICE_STATE_DIR', str(tmp_path))
    for key in ('HEOBRAIN_PUBLIC_RAG_DB', 'HEOBRAIN_PUBLIC_RAG_PYTHON', 'HEOBRAIN_PUBLIC_RAG_MODEL_CACHE'):
        monkeypatch.delenv(key, raising=False)
    return index


def test_public_search_selects_exact_passages_from_distinct_sources(tmp_path, monkeypatch):
    quote = '  공개 기술 문서의 원문 문장입니다.  '
    index = build_index(tmp_path, monkeypatch, [
        ('https://docs.example.org/stable', 7, quote, .95),
        ('https://docs.example.org/stable', 9, '같은 기사', .92),
        ('https://papers.example.org/study', 14, '공개 논문 원문', .78),
        ('https://news.example.org/outlier', 5, '관련 없는 소식', .12),
        ('https://localhost/internal', 5, '비공개 주소', .99),
        ('https://admin@news.example.org/story', 5, '자격 증명 주소', .99),
    ])
    monkeypatch.setattr(public_evidence, '_query_vector',
                        lambda *_: [1.0] + [0.0] * 383)
    before = index.read_bytes()
    results = public_evidence.find_public_evidence('공개 기술 자료', limit=4)
    assert [r['url'] for r in results] == [
        'https://docs.example.org/stable', 'https://papers.example.org/study',
    ]
    expected_hash = hashlib.sha256(quote.encode('utf-8')).hexdigest()
    expected_id = hashlib.sha256(json.dumps(
        ['https://docs.example.org/stable', 'b' * 64, 7, expected_hash],
        ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')).hexdigest()
    assert results[0] == {
        'id': expected_id, 'url': 'https://docs.example.org/stable', 'title': '공개 기사 1',
        'paragraph': 7, 'quote': quote, 'source_sha256': 'b' * 64,
        'quote_sha256': expected_hash,
    }
    assert index.read_bytes() == before
    assert public_evidence.find_public_evidence(
        '공개 기술 자료', exclude_urls=tuple(r['url'] for r in results),
    ) == []


def test_wrong_model_index_is_rejected_before_starting_worker(tmp_path, monkeypatch):
    build_index(tmp_path, monkeypatch, model='different-model')

    def unexpected_worker(*_):
        pytest.fail('invalid index must not start the model worker')

    monkeypatch.setattr(public_evidence, '_query_vector', unexpected_worker)
    with pytest.raises(public_evidence.PublicEvidenceUnavailable):
        public_evidence.find_public_evidence('공개 기술 자료')


def test_runtime_disabled_uses_no_other_provider(tmp_path, monkeypatch):
    build_index(tmp_path, monkeypatch, [
        ('https://docs.example.org/stable', 1, '검증된 공개 문단', .9),
    ])
    monkeypatch.setattr(public_evidence.subprocess, 'run',
                        lambda *args, **kwargs: pytest.fail('unexpected subprocess'))
    with pytest.raises(public_evidence.PublicEvidenceUnavailable):
        public_evidence.find_public_evidence('공개 기술 자료')



def test_worker_busy_retries_no_other_model_and_inherits_no_credentials(tmp_path, monkeypatch):
    root = tmp_path / 'public-rag'
    build_index(tmp_path, monkeypatch, [
        ('https://docs.example.org/stable', 1, '검증된 공개 문단', .9),
    ])
    (root / 'runtime' / 'bin').mkdir(parents=True)
    (root / 'runtime' / 'bin' / 'python').touch()
    (root / 'model-cache').mkdir()
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-key')
    monkeypatch.setenv('HF_TOKEN', 'synthetic-token')
    calls = []

    def fake_worker(args, **kwargs):
        calls.append(args)
        assert args[-2:] == [str(root / 'model-cache'), str(root / 'query.lock')]
        assert kwargs['input'] == '문단 후보'
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        assert 'OPENAI_API_KEY' not in kwargs['env']
        assert 'HF_TOKEN' not in kwargs['env']
        assert kwargs['timeout'] == 12
        return public_evidence.subprocess.CompletedProcess(args, 75, '', '')

    monkeypatch.setattr(public_evidence.subprocess, 'run', fake_worker)
    with pytest.raises(public_evidence.PublicEvidenceUnavailable, match='진행 중'):
        public_evidence.find_public_evidence('문단 후보')
    assert len(calls) == 1



@pytest.mark.parametrize(('available_kib', 'expected_status'), [(799 * 1024, 76), (800 * 1024, 77)])
def test_worker_checks_available_memory_and_pinned_cache_before_importing_model(
        tmp_path, monkeypatch, available_kib, expected_status):
    cache = tmp_path / 'model-cache'
    cache.mkdir()
    lock_path = tmp_path / 'query.lock'
    locked = []
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(
        flock=lambda fd, flags: locked.append(fd), LOCK_EX=2, LOCK_NB=4,
    ))
    monkeypatch.setattr(public_evidence.os, 'O_NOFOLLOW', 0, raising=False)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'query')))

    def available_memory():
        assert locked, 'memory must be checked after obtaining the query lock'
        return available_kib

    def unexpected_model_load(*args, **kwargs):
        pytest.fail('a low-memory host or incomplete model cache must fail before loading FastEmbed')

    monkeypatch.setattr(public_evidence, '_mem_available_kib', available_memory, raising=False)
    monkeypatch.setitem(sys.modules, 'fastembed', SimpleNamespace(TextEmbedding=unexpected_model_load))
    assert public_evidence._run_worker(cache, lock_path) == expected_status
    assert lock_path.is_file()


def test_public_search_drops_weakly_related_passages_below_the_floor(tmp_path, monkeypatch):
    build_index(tmp_path, monkeypatch, [
        ('https://papers.example.org/unrelated', 8, '다른 주제의 논문 문단', .33),
        ('https://papers.example.org/borderline', 3, '경계 아래 문단', .39),
        ('https://docs.example.org/relevant', 4, '질문과 맞는 공식 문서 문단', .52),
    ])
    monkeypatch.setattr(public_evidence, '_query_vector', lambda *_: [1.0] + [0.0] * 383)
    results = public_evidence.find_public_evidence('정보처리기사 실기 계산 문제', limit=4)
    assert [r['url'] for r in results] == ['https://docs.example.org/relevant']


def test_public_search_returns_nothing_when_every_passage_is_weak(tmp_path, monkeypatch):
    build_index(tmp_path, monkeypatch, [('https://papers.example.org/unrelated', 8, '다른 주제의 논문 문단', .36)])
    monkeypatch.setattr(public_evidence, '_query_vector', lambda *_: [1.0] + [0.0] * 383)
    assert public_evidence.find_public_evidence('오픽 등급 올리기', limit=4) == []
