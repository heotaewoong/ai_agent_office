"""Search public evidence with local models only: the legacy snapshot with MiniLM, the source library with its own embedder."""
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
    # 격리된 임베딩 작업 프로세스는 이 파일을 직접 실행한다. office 폴더를 sys.path에 넣으면 office/calendar.py가
    # 표준 calendar를 가려서 requests를 쓰는 모델 로더(fastembed)가 뜨다가 죽는다. 필요한 모듈 하나만 파일 경로로 읽는다.
    import importlib.util

    _spec = importlib.util.spec_from_file_location('evidence_relevance', Path(__file__).resolve().with_name('evidence_relevance.py'))
    _relevance = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_relevance)
    is_evidence_noise, is_topic_candidate, looks_like_reference_list = (
        _relevance.is_evidence_noise, _relevance.is_topic_candidate, _relevance.looks_like_reference_list)


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
# 자료 창고(source_library)에서 운영자가 '초안 근거로 사용'을 켠 링크 자료는 전용 임베딩 모델로 찾는다.
# 2026-11-24 골든셋 v3(질문 100개, 문단 2,887개) 비교에서 고른 한국어와 영어 전용 e5-small 계열 모델이다. 실전 문제 40개 nDCG@10 0.635(MiniLM 0.520).
# 문단을 512토큰까지 한 번에 읽으므로 112토큰 창으로 쪼개지 않고, 인용도 문단 전체를 쓴다. 실험 기록: EC2 ~/.local/state/heobrain-retriever-v3-20261124
_LIBRARY_MODEL = 'exp-models/dragonkue-KoEn-E5-Tiny-ONNX'
_LIBRARY_MODEL_REVISION = '5cf599a8cd6577f2f12a026130ad50132e472cfd'
_LIBRARY_MODEL_DIR = 'dragonkue-KoEn-E5-Tiny-ONNX'
_LIBRARY_MODEL_FILES = {'model.onnx': 149755303, 'tokenizer.json': 2931715}  # 고정한 판의 파일 크기(바이트)
_LIBRARY_POOLING = 'mean'
_LIBRARY_QUERY_PREFIX = 'query: '
_LIBRARY_PASSAGE_PREFIX = 'passage: '
_LIBRARY_TITLE_IN_PASSAGE = True
_LIBRARY_MAX_TOKENS = 512
_LIBRARY_MIN_SIMILARITY = 0.38
_MIN_LIBRARY_WORKER_AVAILABLE_KIB = 600 * 1024
LIBRARY_MODEL = _LIBRARY_MODEL
_MAX_LIBRARY_VECTORS = 30_000
_LIBRARY_BATCH = 32
_MIN_LIBRARY_QUOTE = 60  # 제목 한 줄이나 문장 꼬리처럼 짧은 문단은 근거 후보로 내지 않는다.
_SPAWN_INTERVAL = 15.0
_last_spawn = [0.0]
_PENDING_LIBRARY_SQL = (
    "SELECT p.item_id, p.seq, p.text, i.title FROM passages p JOIN items i ON i.id=p.item_id "
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


def _query_vector(query: str, python: Path, cache: Path, lock_path: Path, *, library: bool = False) -> list[float]:
    """질문을 벡터로 바꾼다. library=True면 자료 창고 전용 모델로, 아니면 예전 공개 색인의 MiniLM으로 계산한다. 다른 모델로 넘어가지 않는다."""
    if not python.is_file() or not cache.is_dir():
        raise PublicEvidenceUnavailable('공개 근거의 로컬 검색 모델 실행 환경이 준비되지 않았습니다.')
    environment = _worker_environment()
    try:
        result = subprocess.run(
            [str(python), '-I', '-B', str(Path(__file__).resolve()), *(['--library-query'] if library else []), str(cache), str(lock_path)],
            input=query, capture_output=True, encoding='utf-8', env=environment, timeout=12, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise PublicEvidenceUnavailable('로컬 공개 근거 검색이 응답하지 않았습니다.') from exc
    if result.returncode == _BUSY_STATUS:
        raise PublicEvidenceUnavailable('다른 공개 근거 검색이 진행 중입니다. 잠시 후 다시 시도해 주세요.')
    if result.returncode == _LOW_MEMORY_STATUS:
        raise PublicEvidenceUnavailable('EC2 메모리 여유가 부족해 공개 근거 검색을 잠시 보류했습니다.')
    if result.returncode == _CACHE_MISSING_STATUS:
        raise PublicEvidenceUnavailable('공개 근거의 오프라인 검색 모델 파일을 확인할 수 없습니다.')
    if result.returncode:
        raise PublicEvidenceUnavailable('공개 근거의 로컬 검색 모델을 읽지 못했습니다.')
    try:
        values = json.loads(result.stdout)
        if not isinstance(values, list) or len(values) != 384:
            raise ValueError('invalid query vector')
        vector = [float(value) for value in values]
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError('invalid query vector magnitude')
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
                (_LIBRARY_MODEL,)).fetchone() is not None
    except sqlite3.Error:
        return False


def _rank_library(path: Path, vector: list[float], exclude_urls, *, area=None) -> list[tuple]:
    """자료 창고에서 '초안 근거로 사용'을 켠 링크 자료의 문단을 전용 모델 벡터로 비교한다. 인용은 벡터를 계산한 구간(문단 전체)을 쓴다."""
    excluded = set(exclude_urls)
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            rows = db.execute(
                "SELECT v.item_id, v.seq, v.part, v.start_char, v.end_char, v.vector, i.url, i.title, i.content_hash, p.text "
                "FROM passage_vectors v JOIN passages p ON p.item_id=v.item_id AND p.seq=v.seq JOIN items i ON i.id=v.item_id "
                "WHERE v.model=? AND i.status='done' AND i.use_as_evidence=1 AND i.kind='link' "
                "AND (? IS NULL OR i.area=?) ORDER BY v.item_id, v.seq, v.part LIMIT ?",
                (_LIBRARY_MODEL, area, area, _MAX_LIBRARY_VECTORS)).fetchall()
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
        if math.isfinite(score) and score >= _LIBRARY_MIN_SIMILARITY:
            ranked.append((-score, (1, item_id, seq, part), url, title.strip()[:500], seq, quote, source_hash))
    return ranked


def find_library_evidence(query: str, *, root, exclude_urls: tuple[str, ...] = (), limit: int = 4, area=None) -> list[dict]:
    """자료 창고의 근거 자료만 찾는다. 근거로 켠 링크의 벡터가 없으면 모델을 띄우지 않는다."""
    query = query.strip()[:_MAX_QUERY_CHARS]
    path = _library_db(root)
    if not query or limit <= 0 or path is None or not _library_has_vectors(path):
        return []
    index, python, cache = _paths()
    vector = _query_vector(query, python, cache, index.parent / 'query.lock', library=True)
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
            lock = index.parent / 'query.lock'
            ranked = _rank_index(db, _query_vector(query, python, cache, lock), exclude_urls) if indexed else []
    except sqlite3.Error as exc:
        raise PublicEvidenceUnavailable('공개 근거 인덱스를 읽지 못했습니다.') from exc
    if library is not None:
        # 자료 창고 문단은 전용 모델로 따로 질문 벡터를 만든다. 모델이 달라 유사도 눈금도 다르므로 하한도 따로 둔다.
        ranked += _rank_library(library, _query_vector(query, python, cache, lock, library=True), exclude_urls, area=area)
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


def _pinned_library_model_dir(cache: Path) -> Path | None:
    model_dir = cache / _LIBRARY_MODEL_DIR / _LIBRARY_MODEL_REVISION
    for name, size in _LIBRARY_MODEL_FILES.items():
        try:
            entry = (model_dir / name).lstat()
        except OSError:
            return None
        if not stat.S_ISREG(entry.st_mode) or entry.st_size != size:
            return None
    return model_dir


def _library_embedder(model_dir: Path):
    """자료 창고 모델로 글 하나를 벡터 하나로 바꾸는 함수를 돌려준다. 한 번에 한 글만 넣어 메모리 최고치를 낮게 둔다."""
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
    tokenizer.enable_truncation(max_length=_LIBRARY_MAX_TOKENS)
    tokenizer.no_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_cpu_mem_arena = False
    session = ort.InferenceSession(str(model_dir / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
    inputs = session.get_inputs()

    def embed(text: str) -> list[float]:
        encoded = tokenizer.encode(text)
        data = {'input_ids': encoded.ids, 'attention_mask': encoded.attention_mask, 'token_type_ids': encoded.type_ids}
        feed = {item.name: np.asarray([data[item.name]], dtype=np.int32 if item.type == 'tensor(int32)' else np.int64)
                for item in inputs}
        hidden = next(value for value in session.run(None, feed) if value.ndim == 3)[0]
        return [float(value) for value in (hidden[0] if _LIBRARY_POOLING == 'cls' else hidden.mean(axis=0))]

    return embed


def _library_passage_text(title: str, text: str) -> str:
    # 골든셋 실험과 같은 글 모양으로 넣는다. 제목을 붙이는 구성이면 "제목 | 문단".
    body = f'{title.strip()} | {text}' if _LIBRARY_TITLE_IN_PASSAGE and isinstance(title, str) and title.strip() else text
    return _LIBRARY_PASSAGE_PREFIX + body


def _run_worker(cache: Path, lock_path: Path, *, library: bool = False) -> int:
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
    if _mem_available_kib() < (_MIN_LIBRARY_WORKER_AVAILABLE_KIB if library else _MIN_WORKER_AVAILABLE_KIB):
        os.close(lock)
        return _LOW_MEMORY_STATUS
    model_dir = _pinned_library_model_dir(cache) if library else _pinned_model_dir(cache)
    if model_dir is None:
        os.close(lock)
        return _CACHE_MISSING_STATUS
    if library:
        print(json.dumps(_library_embedder(model_dir)(_LIBRARY_QUERY_PREFIX + query), allow_nan=False))
        return 0

    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=_PUBLIC_MODEL, cache_dir=str(cache), threads=1,
                             providers=['CPUExecutionProvider'], local_files_only=True,
                             specific_model_path=str(model_dir))
    vector = next(embedder.query_embed([query]))
    print(json.dumps(vector.tolist(), allow_nan=False))
    return 0


def _store_library_vectors(db: sqlite3.Connection, embed, batch: list[tuple]) -> None:
    values = []
    for item_id, seq, text, title in batch:
        numbers = embed(_library_passage_text(title, text))
        norm = math.hypot(*numbers)
        if len(numbers) != 384 or not math.isfinite(norm) or norm <= 0:
            continue
        values.append((item_id, seq, 0, 0, len(text), _LIBRARY_MODEL, _VECTOR.pack(*(number / norm for number in numbers))))
    if not values:
        return
    try:
        with db:
            # 예전 모델이 한 문단을 여러 구간으로 나눠 둔 벡터는 지운다. 문단마다 벡터 하나만 남긴다.
            db.executemany('DELETE FROM passage_vectors WHERE item_id=? AND seq=?', [row[:2] for row in values])
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
    if _mem_available_kib() < _MIN_LIBRARY_WORKER_AVAILABLE_KIB:
        os.close(lock)
        return _LOW_MEMORY_STATUS
    model_dir = _pinned_library_model_dir(cache)
    if model_dir is None:
        os.close(lock)
        return _CACHE_MISSING_STATUS
    try:
        return _embed_library(model_dir, db_path)
    finally:
        os.close(lock)  # 계산을 마친 뒤에 풀어 다음 질문 검색이 바로 쓸 수 있게 한다.


def _embed_library(model_dir: Path, db_path: Path) -> int:
    with closing(sqlite3.connect(db_path, timeout=20)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        try:
            rows = db.execute(_PENDING_LIBRARY_SQL, (_LIBRARY_MODEL, _MAX_LIBRARY_VECTORS)).fetchall()
        except sqlite3.Error:
            return 0
        if not rows:
            return 0
        embed = _library_embedder(model_dir)
        for start in range(0, len(rows), _LIBRARY_BATCH):
            _store_library_vectors(db, embed, rows[start:start + _LIBRARY_BATCH])
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--library':
        raise SystemExit(_run_library_worker(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])))
    if len(sys.argv) == 4 and sys.argv[1] == '--library-query':
        raise SystemExit(_run_worker(Path(sys.argv[2]), Path(sys.argv[3]), library=True))
    raise SystemExit(_run_worker(Path(sys.argv[1]), Path(sys.argv[2])))
