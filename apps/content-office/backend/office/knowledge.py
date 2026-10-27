"""Local, manifest-bound Markdown retrieval; excerpts are evidence, never authority."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import unicodedata


# Groups are ANDed; words within each group are alternatives. This deliberately
# extracts candidates rather than treating a historical document as policy.
_CONTRACTS = {
    "C01": ("원고 승인 후 제작", (("원고", "source"), ("승인", "approve"), ("제작", "미디어", "derive"))),
    "C02": ("동일 판본의 독립 비평·평가", (("critique", "비평"), ("eval", "평가"))),
    "C03": ("중대 지적 보류", (("중대", "critical", "치명"), ("보류", "차단", "block"))),
    "C04": ("판본별 두 승인", (("승인", "approve"), ("①", "②", "hash", "해시", "판본", "원고", "출고"))),
    "C05": ("실제 입력에 따른 캐시", (("cache", "캐시"), ("prompt", "schema", "프롬프트", "rubric", "messages"))),
    "C06": ("성공 자산 보존", (("자산", "asset"), ("보존", "저장", "재사용", "persist"))),
    "C07": ("부모 판본 결합", (("부모", "parent"), ("hash", "해시", "판본", "version"))),
    "C08": ("별도 영속 작업자", (("worker", "작업자"), ("sqlite", "영속", "fastapi", "http"))),
    "C09": ("외부 결과 불명 대사", (("unknown", "불명", "응답 유실"), ("조회", "대사", "reconcile", "재전송"))),
    "C10": ("영상 선택 분기", (("영상", "video"), ("off", "선택", "분기"))),
    "C11": ("기존 엔진 검증 경계", (("verified_state", "dry-run", "선기록", "실제 음성 길이"),)),
    "C12": ("로컬 음성과 유료 대체 제한", (("wsl", "windows", "fallback"), ("tts", "voice", "음성", "유료"))),
    "C13": ("근거와 불확실성 표시", (("근거", "source", "출처"), ("위치", "시각", "확인일", "불확실", "claim"))),
    "C14": ("서버 신원·권한 검사", (("서버", "server"), ("신원", "권한", "인증", "actor"))),
    "C15": ("열린 비용과 예산 한도", (("예산", "budget", "비용"), ("예약", "원자", "상한", "한도", "reservation"))),
    "C16": ("기존 native 책임 재사용", (("native", "hermes"), ("예약", "기억", "owner", "run_id"))),
    "C17": ("미디어와 실제 출고 검수", (("srt", "자막", "mp4", "커버"), ("검수", "검증", "업로드", "공개"))),
    "C18": ("사용자 상태와 접근성", (("키보드", "모바일", "포커스", "빈 상태", "다음 행동"),)),
    "C19": ("외부 문서와 실행 권한 분리", (("원문", "자료", "문서"), ("명령", "임의 shell", "임의 path", "등록 자료"))),
    "C20": ("승인 무효화와 원격 취소 분리", (("승인", "무효화"), ("원격", "예약 취소", "외부 예약"))),
}


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _contained(workspace: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError("path must stay inside the workspace")
    return resolved


def _source_kind(path: str) -> str:
    parts = PurePosixPath(path).parts
    if "fixtures" in parts:
        return "fixture"
    if any(p in {"vendor", "node_modules"} or p.endswith(".dist-info") for p in parts):
        return "vendor_documentation"
    if "input-snapshots" in parts or "local-docs" in parts or "snapshot" in PurePosixPath(path).name:
        return "historical_snapshot"
    return "database_document" if parts[0] == "database" else "research_document"


def _candidate_contracts(text: str, start_line: int, source_kind: str) -> list[dict]:
    if source_kind in {"fixture", "vendor_documentation"}:
        return []
    evidence = []
    for offset, line in enumerate(text.splitlines()):
        normalized = _normalized(line)
        for contract_id, (title, groups) in _CONTRACTS.items():
            if all(any(word in normalized for word in group) for group in groups):
                evidence.append({"contract_id": contract_id, "title": title, "line": start_line + offset,
                                 "excerpt": line, "status": "candidate_evidence"})
    return evidence


def _sections(text: str, source_kind: str) -> list[dict]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    starts = []
    hierarchy = []
    fence = None
    for number, line in enumerate(lines, 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            symbol = marker[1][0]
            if fence is None:
                fence = (symbol, len(marker[1]))
            elif symbol == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            while hierarchy and hierarchy[-1][0] >= level:
                hierarchy.pop()
            hierarchy.append((level, title))
            starts.append((number, title, [title for _, title in hierarchy]))
    if not starts or starts[0][0] != 1:
        starts.insert(0, (1, "(서문)", []))
    sections = []
    for position, (start, title, headings) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        body = "".join(lines[start - 1:end])
        sections.append({"id": f"L{start}", "title": title, "heading_path": headings,
                         "start_line": start, "end_line": end, "text": body,
                         "contracts": _candidate_contracts(body, start, source_kind)})
    return sections


def build_knowledge_index(workspace, manifest_path, output_path) -> dict:
    """Read every registered Markdown fully, verify hashes, then atomically index.

    Manifest paths are POSIX-relative paths under ``database`` or ``research``.
    Validation failures leave any previous index intact. No network or model is used.
    """
    workspace = Path(workspace).resolve(strict=True)
    manifest_path = _contained(workspace, manifest_path)
    output_path = _contained(workspace, output_path)
    if output_path == manifest_path or output_path.suffix.casefold() != ".json":
        raise ValueError("output must be a separate JSON file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, list):
        raise ValueError("manifest must be a list")
    documents, canonical, seen_paths = [], {}, set()
    for record in manifest:
        path = record.get("path") if isinstance(record, dict) else None
        if not isinstance(path, str) or "\\" in path:
            raise ValueError("invalid Markdown source path")
        logical = PurePosixPath(path)
        if logical.is_absolute() or ".." in logical.parts or not logical.parts or logical.parts[0] not in {"database", "research"} or logical.suffix.casefold() != ".md":
            raise ValueError("source must be registered workspace Markdown")
        path = str(logical)
        if path in seen_paths:
            raise ValueError("duplicate manifest path")
        seen_paths.add(path)
        source = _contained(workspace, path)
        if source.relative_to(workspace).parts[0] not in {"database", "research"}:
            raise ValueError("resolved source must stay inside registered source roots")
        if source == output_path or source == manifest_path:
            raise ValueError("output cannot overwrite a source")
        expected_hash = record.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            raise ValueError("invalid manifest SHA-256")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_hash.lower():
            raise ValueError(f"hash drift: {path}")
        text = raw.decode("utf-8")
        kind = _source_kind(path)
        duplicate_of = canonical.get(digest)
        canonical.setdefault(digest, path)
        documents.append({"path": path, "sha256": digest, "bytes": len(raw),
                          "lines": len(text.splitlines()), "source_kind": kind,
                          "duplicate_of": duplicate_of, "text": text,
                          "sections": _sections(text, kind)})
    index = {"schema_version": 1, "built_at": datetime.now(timezone.utc).isoformat(),
             "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
             "policy": {"local_only": True, "automatic_policy_promotion": False, "external_model_transfer": False},
             "documents": documents}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(index, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"documents": len(documents), "unique_documents": len(canonical),
            "duplicate_documents": len(documents) - len(canonical),
            "sections": sum(len(d["sections"]) for d in documents),
            "source_bytes": sum(d["bytes"] for d in documents),
            "manifest_sha256": index["manifest_sha256"], "output_path": str(output_path)}


def search_knowledge(index_path, query, limit=10) -> list[dict]:
    """Return locally matched sections, grouping exact copies by their source hash.

    Whitespace-separated terms must all occur in the section/path. Korean substring
    matching and Unicode NFKC normalization need no tokenizer or external service.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    terms = _normalized(query).split()
    if not terms:
        return []
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    if index.get("schema_version") != 1 or not isinstance(index.get("documents"), list):
        raise ValueError("unsupported knowledge index")
    duplicates = defaultdict(list)
    for document in index["documents"]:
        if document["duplicate_of"]:
            duplicates[document["duplicate_of"]].append(document["path"])
    hits = []
    for document in index["documents"]:
        if document["duplicate_of"]:
            continue
        for section in document["sections"]:
            paths = "\n".join([document["path"], *duplicates[document["path"]]])
            haystack = _normalized(paths + "\n" + document["sha256"] + "\n" + section["title"] + "\n" + section["text"])
            if not all(term in haystack for term in terms):
                continue
            matching_lines = [line for line in section["text"].splitlines() if any(term in _normalized(line) for term in terms)]
            excerpt = "\n".join(matching_lines)[:1200]
            hits.append({"path": document["path"], "sha256": document["sha256"],
                         "source_kind": document["source_kind"], "section_id": section["id"],
                         "section": section["title"], "heading_path": section["heading_path"],
                         "start_line": section["start_line"], "end_line": section["end_line"],
                         "excerpt": excerpt, "duplicate_paths": duplicates[document["path"]],
                         "contracts": section["contracts"],
                         "score": sum(haystack.count(term) for term in terms)})
    hits.sort(key=lambda hit: (-hit["score"], hit["path"], hit["start_line"]))
    return hits[:limit]
