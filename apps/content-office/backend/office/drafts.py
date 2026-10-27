"""Register editor-written Markdown drafts beside a job. Never approves, renders or publishes."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

from .store import Store, WorkflowError, canonical

STATUS_MARKERS = ("개선초안", "미게시", "미승인")
SOURCE_HEADING = "출처와 확인 범위"


def _sections(text):
    """Split on level-2 headings; returns the preamble and {heading: body}."""
    parts = re.split(r"(?m)^## +(.+?)\s*$", text)
    return parts[0], {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def _title_and_rest(text):
    match = re.match(r"\s*# +(.+?)\s*\n", text)
    if not match:
        raise WorkflowError("초안 첫 줄에 # 제목이 필요합니다")
    rest = text[match.end():]
    # The file's status label is for editors; readers never see it.
    rest = "\n".join(line for line in rest.splitlines() if not (line.startswith(">") and any(m in line for m in STATUS_MARKERS)))
    return match.group(1).strip(), rest


def _table(block):
    rows = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return []
    cells = lambda row: [cell.strip() for cell in row.strip("|").split("|")]
    header = cells(rows[0])
    return [dict(zip(header, cells(row))) for row in rows[2:]]


def parse_article(text):
    title, rest = _title_and_rest(text)
    # The blog export appends canonical sources from job evidence; a second copy would repeat them.
    body = re.split(r"(?m)^## +" + re.escape(SOURCE_HEADING) + r"\s*$", rest)[0].strip()
    return title, body


def parse_script(text):
    title, rest = _title_and_rest(text)
    _, sections = _sections(rest)
    scenes = []
    for row in _table(rest.split("\n## ")[0]):
        scene = {"narration": row.get("내레이션", ""), "caption": row.get("화면 자막", ""), "visual": row.get("화면 유형") or row.get("화면 구성", "")}
        if row.get("연출 메모"):
            scene["direction"] = row["연출 메모"]
        if not scene["narration"] or not scene["caption"]:
            raise WorkflowError("대본 표의 각 장면에 내레이션과 화면 자막이 필요합니다")
        scenes.append(scene)
    thumbnails = [{"title": row["제목"], "subtitle": row.get("보조 문구", ""), "angle": row.get("관점", "")} for row in _table(sections.get("썸네일 문구", "")) if row.get("제목")]
    tags = [tag.strip() for tag in re.split(r"[,\n]", sections.get("태그", "")) if tag.strip()]
    video = {"title": title, "description": sections.get("설명란", "").strip(), "tags": tags, "scenes": scenes}
    if thumbnails:
        video["thumbnails"] = thumbnails
    return video


def load_folder(folder):
    folder = Path(folder)
    article_path, script_path = folder / "article.md", folder / "script.md"
    article = article_path.read_text(encoding="utf-8")
    title, body = parse_article(article)
    draft = {"title": title, "body": body, "source_files": [], "note": "편집자가 작성한 미승인 초안입니다. 편집기로 불러와 저장하면 새 원고 버전으로 재검수합니다."}
    draft["source_files"].append({"name": article_path.name, "path": str(article_path), "sha256": hashlib.sha256(article.encode()).hexdigest()})
    if script_path.is_file():
        script = script_path.read_text(encoding="utf-8")
        draft["video"] = parse_script(script)
        draft["source_files"].append({"name": script_path.name, "path": str(script_path), "sha256": hashlib.sha256(script.encode()).hexdigest()})
    return draft


def match_job(store, draft):
    """Pick the job whose evidence IDs the draft cites; refuse ambiguous or unmatched drafts."""
    cited = set(re.findall(r"\[([A-Z]+\d+)\]", draft["body"]))
    matches = [job for job in store.jobs() if cited & {e.get("id") for e in (job.get("article") or {}).get("evidence", [])}]
    if len(matches) != 1:
        raise WorkflowError(f"초안이 인용한 근거 ID {sorted(cited)}로 작업 하나를 특정하지 못했습니다. --job으로 지정하세요")
    return matches[0]["id"]


def register_folder(store, folder, job_id=None):
    draft = load_folder(folder)
    job_id = job_id or match_job(store, draft)
    known = {e.get("id") for e in store.job(job_id)["article"].get("evidence", [])}
    draft["evidence_ids_cited"] = sorted(set(re.findall(r"\[([A-Z]+\d+)\]", draft["body"])))
    draft["evidence_ids_missing"] = sorted(known - set(draft["evidence_ids_cited"]))
    return store.add_draft(job_id, draft)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", help="article.md와 script.md가 있는 초안 폴더")
    parser.add_argument("--job", help="자동 매칭 대신 지정할 작업 ID (폴더 하나일 때)")
    args = parser.parse_args()
    if args.job and len(args.folders) != 1:
        parser.error("--job은 폴더 하나에만 사용할 수 있습니다")
    from .bootstrap import default_store
    store = default_store()
    try:
        for folder in args.folders:
            record = register_folder(store, folder, args.job)
            print(canonical({"folder": folder, "job_id": record["job_id"], "draft_id": record["id"], "title": record["title"], "body_chars": len(record["body"]), "scenes": len((record.get("video") or {}).get("scenes", [])), "evidence_ids_missing": record["evidence_ids_missing"]}))
    except WorkflowError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
