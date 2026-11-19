"""Build the public article index from an explicitly reviewed URL list and saved evidence."""

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit


MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REPO = "models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
DIMENSIONS = 384
TOKEN_LIMIT = 112


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprints(url, source_hash, paragraph, quote):
    encoded = json.dumps([url, source_hash, paragraph, sha(quote)], separators=(",", ":"), ensure_ascii=False)
    return sha(encoded)


def source_location(url):
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port:
        return None
    return parts.hostname.lower(), parts.path.rstrip("/"), parts.query


def get_titles(db_path, urls):
    locations = {source_location(url) for url in urls}
    found = {}

    def search(node):
        if isinstance(node, dict):
            title = node.get("title")
            if isinstance(title, str) and title.strip():
                for field in ("url", "source_url", "canonical_url"):
                    url = node.get(field)
                    if isinstance(url, str) and url.startswith("https://") and len(url) <= 2048:
                        try:
                            location = source_location(url)
                        except ValueError:
                            continue
                        if location and location in locations:
                            found.setdefault(location, title.strip())
            for value in node.values():
                if isinstance(value, (dict, list)):
                    search(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    search(value)

    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        for table in ("articles", "jobs"):
            for (item,) in db.execute("SELECT data FROM " + table):
                search(json.loads(item))
    return found


def source_snapshots(evidence_dir, urls):
    latest = {}
    for path in sorted(evidence_dir.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        url = report.get("url")
        if report.get("source_kind") != "http_article_body" or url not in urls:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", str(report.get("source_sha256", ""))):
            continue
        if url not in latest or report["retrieved_at"] > latest[url]["retrieved_at"]:
            latest[url] = report
    if not latest or latest.keys() != urls:
        raise ValueError("Every explicit HTTPS URL needs a saved public HTML article body.")
    return latest


def load_passages(snapshots, titles, tokenizer):
    unique = {}
    for url, report in sorted(snapshots.items()):
        title = titles.get(source_location(url))
        if not title:
            raise ValueError("A reviewed source has no matching article title.")
        source_hash = report["source_sha256"]
        for number, text in enumerate(report["paragraphs"], 1):
            if not isinstance(text, str) or not text.strip():
                continue
            offsets = tokenizer.encode(text, add_special_tokens=False).offsets
            for start in range(0, len(offsets), TOKEN_LIMIT):
                first = offsets[start][0]
                last = offsets[min(len(offsets), start + TOKEN_LIMIT) - 1][1]
                quote = text[first:last].strip()
                if quote and len(quote) <= 1800:
                    eid = fingerprints(url, source_hash, number, quote)
                    unique.setdefault(eid, (url, title, number, quote, source_hash))
    if not unique or len(unique) > 4096:
        raise ValueError("The reviewed corpus must contain 1–4,096 public passages.")
    return unique


def build(state):
    from fastembed import TextEmbedding
    from tokenizers import Tokenizer

    dest = state / "public-rag"
    cache = dest / "model-cache"
    urls = set(json.loads((dest / "public-urls.json").read_text(encoding="utf-8")))
    if len(urls) < 2 or any(not source_location(url) for url in urls):
        raise ValueError("Provide at least two reviewed HTTPS article URLs.")
    snapshots = source_snapshots(state / "evidence", urls)
    titles = get_titles(state / "office.sqlite3", urls)
    saved_titles = json.loads((dest / "public-titles.json").read_text(encoding="utf-8"))
    if saved_titles.keys() != urls or any(not isinstance(title, str) or not title.strip() for title in saved_titles.values()):
        raise ValueError("Every reviewed URL needs a recorded public title.")
    for url, title in saved_titles.items():
        titles.setdefault(source_location(url), title.strip())
    revision = (cache / REPO / "refs" / "main").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid offline tokenizer revision.")
    checkpoint = cache / REPO / "snapshots" / revision
    if not all((checkpoint / name).is_file() for name in ("model_optimized.onnx", "tokenizer.json", "config.json", "tokenizer_config.json", "special_tokens_map.json")):
        raise ValueError("The offline MiniLM snapshot is incomplete.")
    tokenizer = Tokenizer.from_file(str(checkpoint / "tokenizer.json"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    passages = load_passages(snapshots, titles, tokenizer)
    corpus_hash = sha("\n".join(sorted(passages)))

    with open(dest / "query.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        available = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
        if available < 900 * 1024:
            raise RuntimeError("Public corpus rebuild needs at least 900 MiB of available memory.")
        embedder = TextEmbedding(MODEL, threads=1, local_files_only=True, specific_model_path=str(checkpoint))
        fd, tmp_name = tempfile.mkstemp(prefix=".index-", suffix=".sqlite3", dir=dest)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with closing(sqlite3.connect(tmp)) as db, db:
                db.execute("CREATE TABLE public_index_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                db.execute("""CREATE TABLE public_passages(
                    id INTEGER PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,paragraph INTEGER NOT NULL,
                    quote TEXT NOT NULL,source_sha256 TEXT NOT NULL,vector BLOB NOT NULL)""")
                rows = list(passages.values())
                for row, vector in zip(rows, embedder.embed([row[3] for row in rows], batch_size=16), strict=True):
                    values = vector.tolist()
                    norm = math.hypot(*values)
                    if len(values) != DIMENSIONS or not math.isfinite(norm) or norm <= 0:
                        raise ValueError("Unexpected MiniLM vector.")
                    db.execute("INSERT INTO public_passages(url,title,paragraph,quote,source_sha256,vector) VALUES(?,?,?,?,?,?)",
                               (*row, struct.pack("<384f", *(value / norm for value in values))))
                db.executemany("INSERT INTO public_index_meta VALUES(?,?)", [
                    ("schema_version", "1"), ("embedding_model", MODEL), ("embedding_dimensions", str(DIMENSIONS)),
                    ("corpus_sha256", corpus_hash),
                ])
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Public SQLite integrity check failed.")
            tmp.replace(dest / "index.sqlite3")
        finally:
            if tmp.exists():
                tmp.unlink()
    print(json.dumps({"articles": len(snapshots), "passages": len(passages), "corpus_sha256": corpus_hash,
                      "model_revision": revision, "dimensions": DIMENSIONS}))


if __name__ == "__main__":
    flags = argparse.ArgumentParser()
    flags.add_argument("--office-state", type=Path, required=True)
    args = flags.parse_args()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    build(args.office_state.resolve(strict=True))
