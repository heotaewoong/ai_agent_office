"""Search a public-only SQLite snapshot with the local multilingual MiniLM model."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import struct
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit


_PUBLIC_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
_VECTOR = struct.Struct('<384f')
_MAX_QUERY_CHARS = 800
_MAX_PASSAGES = 4096
_MAX_RESULTS = 6
_MIN_SIMILARITY = 0.28
_BUSY_STATUS = 75
_LOW_MEMORY_STATUS = 76
_CACHE_MISSING_STATUS = 77
_MIN_WORKER_AVAILABLE_KIB = 800 * 1024
_MODEL_REVISION = 'faf4aa4225822f3bc6376869cb1164e8e3feedd0'
_MODEL_CACHE_NAME = 'models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q'
_MODEL_FILES = ('model_optimized.onnx', 'config.json', 'tokenizer.json',
                'tokenizer_config.json', 'special_tokens_map.json')


class PublicEvidenceUnavailable(RuntimeError):
    """The isolated public search has no usable index or model worker."""


def public_evidence_id(url: str, source_sha256: str, paragraph: int, quote_sha256: str) -> str:
    identity = json.dumps([url, source_sha256, paragraph, quote_sha256],
                          ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


def _paths() -> tuple[Path, Path, Path]:
    state = Path(os.environ.get('OFFICE_STATE_DIR') or
                 Path.home() / '.local/state/heobrain-content-office') / 'public-rag'
    return (
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_DB') or state / 'index.sqlite3').expanduser().absolute(),
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_PYTHON') or state / 'runtime/bin/python').expanduser().absolute(),
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_MODEL_CACHE') or state / 'model-cache').expanduser().absolute(),
    )


def _query_vector(query: str, python: Path, cache: Path, lock_path: Path) -> list[float]:
    if not python.is_file() or not cache.is_dir():
        raise PublicEvidenceUnavailable('공개 근거의 로컬 MiniLM 실행 환경이 준비되지 않았습니다.')
    environment = {
        'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TRANSFORMERS_OFFLINE': '1',
        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
    }
    try:
        result = subprocess.run(
            [str(python), '-I', '-B', str(Path(__file__).resolve()), str(cache), str(lock_path)],
            input=query, capture_output=True, encoding='utf-8', env=environment, timeout=12, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise PublicEvidenceUnavailable('로컬 공개 근거 검색이 응답하지 않았습니다.') from exc
    if result.returncode == _BUSY_STATUS:
        raise PublicEvidenceUnavailable('다른 공개 근거 검색이 진행 중입니다. 잠시 후 다시 시도해 주세요.')
    if result.returncode == _LOW_MEMORY_STATUS:
        raise PublicEvidenceUnavailable('EC2 메모리 여유가 부족해 공개 근거 검색을 잠시 보류했습니다.')
    if result.returncode == _CACHE_MISSING_STATUS:
        raise PublicEvidenceUnavailable('공개 근거의 오프라인 MiniLM 모델 파일을 확인할 수 없습니다.')
    if result.returncode:
        raise PublicEvidenceUnavailable('공개 근거의 로컬 MiniLM 모델을 읽지 못했습니다.')
    try:
        values = json.loads(result.stdout)
        if not isinstance(values, list) or len(values) != 384:
            raise ValueError('invalid MiniLM query vector')
        vector = [float(value) for value in values]
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError('invalid MiniLM query vector magnitude')
        return [value / norm for value in vector]
    except (TypeError, ValueError, OverflowError) as exc:
        raise PublicEvidenceUnavailable('공개 근거 검색의 벡터를 확인할 수 없습니다.') from exc


def _hex_hash(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _safe_reference(url: str) -> bool:
    from .evidence import reference_url
    from .store import WorkflowError

    if not isinstance(url, str) or not url or len(url) > 2048 or re.search(r'[\x00-\x20\\]', url):
        return False
    try:
        reference_url(url)
        host = urlsplit(url).hostname or ''
        return '.' in host or ':' in host
    except (ValueError, WorkflowError):
        return False


def _search(db: sqlite3.Connection, vector: list[float], exclude_urls: tuple[str, ...],
            limit: int) -> list[dict]:
    ranked = []
    excluded = set(exclude_urls)
    passages = db.execute(
        'SELECT id, url, title, paragraph, quote, source_sha256, vector FROM public_passages '
        'ORDER BY id LIMIT ?', (_MAX_PASSAGES + 1,),
    )
    for offset, (row_id, url, title, paragraph, quote, source_hash, blob) in enumerate(passages):
        if offset == _MAX_PASSAGES:
            raise PublicEvidenceUnavailable('공개 근거 인덱스의 크기가 이 서버의 검색 범위를 넘었습니다.')
        if (not isinstance(blob, bytes) or len(blob) != _VECTOR.size or url in excluded or
                not isinstance(paragraph, int) or paragraph < 1 or not _hex_hash(source_hash) or
                not isinstance(title, str) or not title.strip() or len(title) > 500 or
                not isinstance(quote, str) or not quote.strip() or len(quote) > 1800):
            continue
        score = sum(a * b for a, b in zip(vector, _VECTOR.unpack(blob), strict=True))
        if math.isfinite(score) and score >= _MIN_SIMILARITY:
            ranked.append((-score, row_id, url, title, paragraph, quote, source_hash))

    matches = []
    for _, _, url, title, paragraph, quote, source_hash in sorted(ranked):
        if url in excluded or not _safe_reference(url):
            continue
        quote_hash = hashlib.sha256(quote.encode('utf-8')).hexdigest()
        matches.append({
            'id': public_evidence_id(url, source_hash, paragraph, quote_hash),
            'url': url, 'title': title, 'paragraph': paragraph, 'quote': quote,
            'source_sha256': source_hash, 'quote_sha256': quote_hash,
        })
        excluded.add(url)
        if len(matches) == limit:
            break
    return matches


def find_public_evidence(query: str, *, exclude_urls: tuple[str, ...] = (), limit: int = 4) -> list[dict]:
    """Return at most one exact supporting excerpt per public URL."""
    query = query.strip()[:_MAX_QUERY_CHARS]
    if not query or limit <= 0:
        return []
    index, python, cache = _paths()
    if not index.is_file():
        raise PublicEvidenceUnavailable('공개 근거 인덱스가 아직 준비되지 않았습니다.')
    try:
        with closing(sqlite3.connect(index.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            db.execute('BEGIN')
            meta = dict(db.execute('SELECT key, value FROM public_index_meta'))
            if (meta.get('schema_version') != '1' or meta.get('embedding_model') != _PUBLIC_MODEL or
                    meta.get('embedding_dimensions') != '384' or not _hex_hash(meta.get('corpus_sha256'))):
                raise PublicEvidenceUnavailable('공개 근거 인덱스의 모델 정보를 확인할 수 없습니다.')
            if not db.execute('SELECT 1 FROM public_passages LIMIT 1').fetchone():
                return []
            vector = _query_vector(query, python, cache, index.parent / 'query.lock')
            return _search(db, vector, exclude_urls, min(limit, _MAX_RESULTS))
    except sqlite3.Error as exc:
        raise PublicEvidenceUnavailable('공개 근거 인덱스를 읽지 못했습니다.') from exc


def _mem_available_kib() -> int:
    try:
        for line in Path('/proc/meminfo').read_text(encoding='ascii').splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _pinned_model_dir(cache: Path) -> Path | None:
    model_dir = cache / _MODEL_CACHE_NAME / 'snapshots' / _MODEL_REVISION
    for name in _MODEL_FILES:
        try:
            entry = (model_dir / name).lstat()
        except OSError:
            return None
        if not stat.S_ISREG(entry.st_mode) or not entry.st_size:
            return None
    return model_dir


def _run_worker(cache: Path, lock_path: Path) -> int:
    import fcntl

    query = sys.stdin.buffer.read(_MAX_QUERY_CHARS * 4 + 1).decode('utf-8')
    if not query or len(query) > _MAX_QUERY_CHARS:
        return 2
    # Keep the descriptor open until process exit so a second model cannot load during teardown.
    lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock)
        return _BUSY_STATUS
    if _mem_available_kib() < _MIN_WORKER_AVAILABLE_KIB:
        os.close(lock)
        return _LOW_MEMORY_STATUS
    model_dir = _pinned_model_dir(cache)
    if model_dir is None:
        os.close(lock)
        return _CACHE_MISSING_STATUS

    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=_PUBLIC_MODEL, cache_dir=str(cache), threads=1,
                             providers=['CPUExecutionProvider'], local_files_only=True,
                             specific_model_path=str(model_dir))
    vector = next(embedder.query_embed([query]))
    print(json.dumps(vector.tolist(), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(_run_worker(Path(sys.argv[1]), Path(sys.argv[2])))
