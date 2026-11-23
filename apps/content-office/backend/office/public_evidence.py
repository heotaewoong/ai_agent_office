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
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .evidence_relevance import is_evidence_noise, is_topic_candidate, looks_like_reference_list
else:
    # The isolated local embedding subprocess runs this file directly.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evidence_relevance import is_evidence_noise, is_topic_candidate, looks_like_reference_list


_PUBLIC_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
_VECTOR = struct.Struct('<384f')
_MAX_QUERY_CHARS = 800
_MAX_PASSAGES = 4096
_MAX_RESULTS = 6
# 2026-11-23 운영 색인(85문단)에서 잰 값: 주제가 다른 기획의 최고 유사도는 0.32~0.38,
# 실제로 관련된 문단은 0.47~0.60이었다. 0.28에서는 정보처리기사 기획에 AI 논문 문단이 후보로 떴다.
# 관련 없는 문단을 기획 선택⓪ 후보로 보여 주지 않도록 하한을 0.40으로 올린다.
_MIN_SIMILARITY = 0.40
_BUSY_STATUS = 75
_LOW_MEMORY_STATUS = 76
_CACHE_MISSING_STATUS = 77
_MIN_WORKER_AVAILABLE_KIB = 800 * 1024
_MODEL_REVISION = 'faf4aa4225822f3bc6376869cb1164e8e3feedd0'
_MODEL_CACHE_NAME = 'models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q'
_MODEL_FILES = ('model_optimized.onnx', 'config.json', 'tokenizer.json',
                'tokenizer_config.json', 'special_tokens_map.json')
PUBLIC_MODEL = _PUBLIC_MODEL
# 자료 창고(source_library)에서 운영자가 '초안 근거로 사용'을 켠 링크 자료도 같은 모델·같은 하한으로 찾는다.
_MAX_LIBRARY_VECTORS = 30_000
_LIBRARY_BATCH = 32
_LIBRARY_TOKENS = 112
_MIN_LIBRARY_QUOTE = 60  # 제목 한 줄이나 문장 꼬리처럼 짧은 구간은 근거 후보로 내지 않는다.
_SPAWN_INTERVAL = 15.0
_last_spawn = [0.0]
_PENDING_LIBRARY_SQL = (
    "SELECT p.item_id, p.seq, p.text FROM passages p JOIN items i ON i.id=p.item_id "
    "WHERE i.status='done' AND i.use_as_evidence=1 AND i.kind='link' AND NOT EXISTS ("
    "SELECT 1 FROM passage_vectors v WHERE v.item_id=p.item_id AND v.seq=p.seq AND v.model=?) "
    "ORDER BY i.updated_at, p.item_id, p.seq LIMIT ?")


class PublicEvidenceUnavailable(RuntimeError):
    """The isolated public search has no usable index or model worker."""


def public_evidence_id(url: str, source_sha256: str, paragraph: int, quote_sha256: str) -> str:
    identity = json.dumps([url, source_sha256, paragraph, quote_sha256],
                          ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


def _state_dir() -> Path:
    return Path(os.environ.get('OFFICE_STATE_DIR') or Path.home() / '.local/state/heobrain-content-office')


def _paths() -> tuple[Path, Path, Path]:
    state = _state_dir() / 'public-rag'
    return (
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_DB') or state / 'index.sqlite3').expanduser().absolute(),
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_PYTHON') or state / 'runtime/bin/python').expanduser().absolute(),
        Path(os.environ.get('HEOBRAIN_PUBLIC_RAG_MODEL_CACHE') or state / 'model-cache').expanduser().absolute(),
    )


def _worker_environment() -> dict:
    return {
        'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TRANSFORMERS_OFFLINE': '1',
        'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
    }


def _query_vector(query: str, python: Path, cache: Path, lock_path: Path) -> list[float]:
    if not python.is_file() or not cache.is_dir():
        raise PublicEvidenceUnavailable('공개 근거의 로컬 MiniLM 실행 환경이 준비되지 않았습니다.')
    environment = _worker_environment()
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


def _rank_index(db: sqlite3.Connection, vector: list[float], exclude_urls) -> list[tuple]:
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
            ranked.append((-score, (0, row_id), url, title, paragraph, quote, source_hash))
    return ranked


def _select(ranked: list[tuple], exclude_urls, limit: int, *, query: str = "") -> list[dict]:
    excluded = set(exclude_urls)
    matches = []
    for _, _, url, title, paragraph, quote, source_hash in sorted(ranked):
        if url in excluded or not _safe_reference(url) or not is_topic_candidate(query, title, quote):
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


def _search(db: sqlite3.Connection, vector: list[float], exclude_urls: tuple[str, ...], limit: int) -> list[dict]:
    return _select(_rank_index(db, vector, exclude_urls), exclude_urls, limit)


def _library_db(root) -> Path | None:
    from .source_library import library_path

    path = library_path(root)
    return path if path.is_file() else None


def _library_has_vectors(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            return db.execute(
                "SELECT 1 FROM passage_vectors v JOIN items i ON i.id=v.item_id "
                "WHERE v.model=? AND i.status='done' AND i.use_as_evidence=1 AND i.kind='link' LIMIT 1",
                (_PUBLIC_MODEL,)).fetchone() is not None
    except sqlite3.Error:
        return False


def _rank_library(path: Path, vector: list[float], exclude_urls, *, area=None) -> list[tuple]:
    """자료 창고에서 '초안 근거로 사용'을 켠 링크 자료의 문단을 같은 모델 벡터로 비교한다. 인용은 맞은 구간만 쓴다."""
    excluded = set(exclude_urls)
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            rows = db.execute(
                "SELECT v.item_id, v.seq, v.part, v.start_char, v.end_char, v.vector, i.url, i.title, i.content_hash, p.text "
                "FROM passage_vectors v JOIN passages p ON p.item_id=v.item_id AND p.seq=v.seq JOIN items i ON i.id=v.item_id "
                "WHERE v.model=? AND i.status='done' AND i.use_as_evidence=1 AND i.kind='link' "
                "AND (? IS NULL OR i.area=?) ORDER BY v.item_id, v.seq, v.part LIMIT ?",
                (_PUBLIC_MODEL, area, area, _MAX_LIBRARY_VECTORS)).fetchall()
    except sqlite3.Error:
        return []
    ranked = []
    for item_id, seq, part, start, end, blob, url, title, source_hash, text in rows:
        if (not isinstance(blob, bytes) or len(blob) != _VECTOR.size or not isinstance(url, str) or url in excluded
                or type(seq) is not int or seq < 1 or not _hex_hash(source_hash) or not isinstance(title, str)
                or not title.strip() or not isinstance(text, str) or type(start) is not int or type(end) is not int):
            continue
        quote = text[start:end].strip()
        if len(quote) < _MIN_LIBRARY_QUOTE or len(quote) > 1800 or is_evidence_noise(quote):
            continue
        score = sum(a * b for a, b in zip(vector, _VECTOR.unpack(blob), strict=True))
        if math.isfinite(score) and score >= _MIN_SIMILARITY:
            ranked.append((-score, (1, item_id, seq, part), url, title.strip()[:500], seq, quote, source_hash))
    return ranked


def find_library_evidence(query: str, *, root, exclude_urls: tuple[str, ...] = (), limit: int = 4, area=None) -> list[dict]:
    """자료 창고의 근거 자료만 찾는다. 근거로 켠 링크의 벡터가 없으면 모델을 띄우지 않는다."""
    query = query.strip()[:_MAX_QUERY_CHARS]
    path = _library_db(root)
    if not query or limit <= 0 or path is None or not _library_has_vectors(path):
        return []
    index, python, cache = _paths()
    vector = _query_vector(query, python, cache, index.parent / 'query.lock')
    return _select(_rank_library(path, vector, exclude_urls, area=area), exclude_urls, min(limit, _MAX_RESULTS), query=query)


def library_worker_available(root) -> bool:
    """벡터 계산은 실행 중인 서버 상태 폴더의 자료 창고에만 한다. 테스트 폴더나 사본은 건드리지 않는다."""
    _, python, cache = _paths()
    try:
        same = Path(root).resolve() == _state_dir().resolve()
    except OSError:
        return False
    return same and python.is_file() and cache.is_dir()


def start_library_vectors(root) -> bool:
    """근거로 켠 링크 문단의 벡터 계산을 백그라운드로 시작한다. 15초 안에 다시 부르면 건너뛴다."""
    if not library_worker_available(root):
        return False
    path = _library_db(root)
    moment = time.monotonic()
    if path is None or moment - _last_spawn[0] < _SPAWN_INTERVAL:
        return False
    _last_spawn[0] = moment
    index, python, cache = _paths()
    try:
        subprocess.Popen(
            [str(python), '-I', '-B', str(Path(__file__).resolve()), '--library', str(cache), str(index.parent / 'query.lock'), str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=_worker_environment(), start_new_session=True, close_fds=True)
    except OSError:
        return False
    return True


def find_public_evidence(query: str, *, exclude_urls: tuple[str, ...] = (), limit: int = 4, area=None) -> list[dict]:
    """Return at most one exact supporting excerpt per public URL."""
    query = query.strip()[:_MAX_QUERY_CHARS]
    if not query or limit <= 0:
        return []
    index, python, cache = _paths()
    if not index.is_file():
        raise PublicEvidenceUnavailable('공개 근거 인덱스가 아직 준비되지 않았습니다.')
    library = _library_db(_state_dir())
    if library is not None and not _library_has_vectors(library):
        library = None
    try:
        with closing(sqlite3.connect(index.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            db.execute('BEGIN')
            meta = dict(db.execute('SELECT key, value FROM public_index_meta'))
            if (meta.get('schema_version') != '1' or meta.get('embedding_model') != _PUBLIC_MODEL or
                    meta.get('embedding_dimensions') != '384' or not _hex_hash(meta.get('corpus_sha256'))):
                raise PublicEvidenceUnavailable('공개 근거 인덱스의 모델 정보를 확인할 수 없습니다.')
            indexed = db.execute('SELECT 1 FROM public_passages LIMIT 1').fetchone() is not None
            if not indexed and library is None:
                return []
            vector = _query_vector(query, python, cache, index.parent / 'query.lock')
            ranked = _rank_index(db, vector, exclude_urls) if indexed else []
    except sqlite3.Error as exc:
        raise PublicEvidenceUnavailable('공개 근거 인덱스를 읽지 못했습니다.') from exc
    if library is not None:
        ranked += _rank_library(library, vector, exclude_urls, area=area)
    return _select(ranked, exclude_urls, min(limit, _MAX_RESULTS), query=query)


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


def _windows(tokenizer, text: str) -> list[tuple[int, int]]:
    # MiniLM은 128토큰까지만 읽으므로 공개 색인을 만들 때처럼 112토큰 구간으로 나눠 계산한다.
    # 마지막 구간이 짧으면 앞 구간과 겹치게 끝 112토큰을 잡는다. 몇 글자짜리 꼬리 구간은 아무 질문에나 비슷하게 나온다.
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    if not offsets:
        return [(0, min(len(text), 1800))]
    starts = list(range(0, len(offsets), _LIBRARY_TOKENS))
    if len(starts) > 1 and len(offsets) - starts[-1] < _LIBRARY_TOKENS // 2:
        starts[-1] = len(offsets) - _LIBRARY_TOKENS
    spans = []
    for first in starts:
        start, end = offsets[first][0], offsets[min(len(offsets), first + _LIBRARY_TOKENS) - 1][1]
        if text[start:end].strip():
            spans.append((start, end))
    return spans or [(0, min(len(text), 1800))]


def _store_library_vectors(db: sqlite3.Connection, embedder, batch: list[tuple]) -> None:
    if not batch:
        return
    values = []
    for (item_id, seq, part, start, end, _), vector in zip(batch, embedder.embed([row[5] for row in batch], batch_size=16), strict=True):
        numbers = vector.tolist()
        norm = math.hypot(*numbers)
        if len(numbers) != 384 or not math.isfinite(norm) or norm <= 0:
            continue
        values.append((item_id, seq, part, start, end, _PUBLIC_MODEL, _VECTOR.pack(*(number / norm for number in numbers))))
    try:
        with db:
            db.executemany('INSERT OR REPLACE INTO passage_vectors(item_id, seq, part, start_char, end_char, model, vector) '
                           'VALUES (?,?,?,?,?,?,?)', values)
    except sqlite3.IntegrityError:
        pass  # 계산하는 동안 자료가 지워졌거나 다시 읽혔다. 다음 실행이 남은 문단을 다시 계산한다.


def _run_library_worker(cache: Path, lock_path: Path, db_path: Path) -> int:
    import fcntl

    # 질문 벡터 작업자와 같은 잠금을 써서 모델을 두 개 동시에 띄우지 않는다.
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
    try:
        return _embed_library(cache, model_dir, db_path)
    finally:
        os.close(lock)  # 계산을 마친 뒤에 풀어 다음 질문 검색이 바로 쓸 수 있게 한다.


def _embed_library(cache: Path, model_dir: Path, db_path: Path) -> int:
    with closing(sqlite3.connect(db_path, timeout=20)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        try:
            rows = db.execute(_PENDING_LIBRARY_SQL, (_PUBLIC_MODEL, _MAX_LIBRARY_VECTORS)).fetchall()
        except sqlite3.Error:
            return 0
        if not rows:
            return 0
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        embedder = TextEmbedding(model_name=_PUBLIC_MODEL, cache_dir=str(cache), threads=1,
                                 providers=['CPUExecutionProvider'], local_files_only=True,
                                 specific_model_path=str(model_dir))
        batch = []
        for position, (item_id, seq, text) in enumerate(rows):
            batch.extend((item_id, seq, part, start, end, text[start:end])
                         for part, (start, end) in enumerate(_windows(tokenizer, text)))
            if len(batch) >= _LIBRARY_BATCH or position == len(rows) - 1:
                _store_library_vectors(db, embedder, batch)
                batch = []
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--library':
        raise SystemExit(_run_library_worker(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])))
    raise SystemExit(_run_worker(Path(sys.argv[1]), Path(sys.argv[2])))
