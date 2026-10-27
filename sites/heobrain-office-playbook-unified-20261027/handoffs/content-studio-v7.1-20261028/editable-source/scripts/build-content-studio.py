"""Export the versioned planning pack. Standard library only; no network or API."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content-studio"
DIST = ROOT / "dist" / "content-studio"
DOWNLOADS = DIST / "downloads"

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def write_archive(path, entries):
    """Stable timestamps avoid changing archives when the reviewed inputs stay the same."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)

def export_source(data):
    target = json.loads((ROOT/"site-target.json").read_text(encoding="utf-8"))
    entries = {}
    paths = ["site-target.json", "scripts/build-content-studio.py", "scripts/validate-content-studio.py", "scripts/check-content-costs.cjs"]
    paths += [p.relative_to(ROOT).as_posix() for p in SOURCE.rglob("*") if p.is_file() and p.suffix in (".md", ".json")]
    paths += [p.relative_to(ROOT).as_posix() for p in DIST.iterdir() if p.is_file() and p.suffix in (".html", ".js", ".css", ".json")]
    paths += [p.relative_to(ROOT).as_posix() for p in DOWNLOADS.iterdir() if p.is_file() and p.suffix in (".md", ".json")]
    for name in sorted(set(paths)):
        path = ROOT/name
        if not path.is_file():
            raise ValueError("Missing portable source: " + name)
        body = path.read_bytes()
        if name == "dist/content-studio/index.html":
            html = body.decode("utf-8")
            for prefix in ("/complete/", "/source-kits/"):
                html = html.replace('href="'+prefix, 'href="'+target["url"]+prefix)
            html = html.replace('href="/"', 'href="'+target["url"]+'/"')
            html = html.replace('href="../content-system.html"', 'href="'+target["url"]+'/content-system.html"')
            body = html.encode("utf-8")
        entries[name] = body
    entries["README.md"] = ("# HeoBrain 콘텐츠 스튜디오 · 편집 가능한 소스\n\n"
        + data["meta"]["version"] + "의 새 콘텐츠 경로만 포함한다. 기존 전체 플레이북은 HTTPS 링크로 연다.\n\n"
        "필요 환경: Python 3.11 이상. JavaScript 검산은 Node.js 18 이상. 추가 패키지 설치는 없다.\n\n"
        "전체 설계는 https://heobrain-office-playbook-20261027.ihtwandy0528.chatgpt.site/content-system.html 의 정본을 먼저 읽는다. integrated-guide.md/json이 있으면 상위 설계의 읽기용 스냅샷이며 이 작업실 코드와 구분한다.\n\n"
        "1. `content-studio/README.md`와 `content-studio/master-guide.md`부터 읽는다.\n"
        "2. Python 표준 라이브러리로 `python scripts/build-content-studio.py`를 실행한다.\n"
        "3. Node가 있으면 `node scripts/check-content-costs.cjs`, `node --check dist/content-studio/app.js`를 확인한다.\n"
        "4. `python scripts/validate-content-studio.py`로 계약·링크·해시·내보내기를 확인한다.\n"
        "5. `python -m http.server 8769 --bind 127.0.0.1 --directory dist` 후 http://127.0.0.1:8769/content-studio/ 를 연다.\n\n"
        "설정·DB·API 키·로그인·회원 원문은 없다. 계산기는 가정을 계산하며 생성·게시·발송·결제를 하지 않는다.\n"
        "사이트 정본은 site-target.json의 기존 Sites 연결 저장소다. 최신 버전·접근 범위를 보존해 병합한다. "
        "source.zip의 예전 사본으로 최신 원격 소스를 덮어쓰지 않는다.\n").encode("utf-8")
    source_manifest = {"version": data["meta"]["version"], "scope": "Editable content-studio source; legacy routes link to existing HTTPS site", "files": [
        {"name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name,body in sorted(entries.items())]}
    entries["SOURCE_MANIFEST.json"] = (json.dumps(source_manifest, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    path = DOWNLOADS/"content-studio-source.zip"
    write_archive(path, entries)
    (DOWNLOADS/"content-studio-source.sha256").write_text(digest(path)+"  content-studio-source.zip\n",encoding="ascii")
    return len(entries), path.stat().st_size

def public_check(text, label):
    checks = [
        r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", r"\\\\wsl", r"/home/[^ /]+",
        r"https://drive\.google\.com/", r"[\w.+-]+@(?:gmail|naver)\.com",
        r"(?i)(?:sk-ant-|sk-proj-|ghp_|github_pat_|AKIA)[A-Za-z0-9_-]{12,}",
        r"(?i)Bearer\s+[A-Za-z0-9_.-]{12,}",
    ]
    for pattern in checks:
        if re.search(pattern, text):
            raise ValueError("Private data pattern in " + label + ": " + pattern)

def table(headers, rows):
    def clean(x):
        if isinstance(x, list):
            x = " · ".join(str(v) for v in x)
        return str(x).replace("|", "/").replace("\n", " ")
    result = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    result.extend("| " + " | ".join(clean(x) for x in row) + " |" for row in rows)
    return "\n".join(result) + "\n"

def main():
    data = json.loads((SOURCE / "content.json").read_text(encoding="utf-8"))
    cost_path = SOURCE / "cost-scenarios.json"
    if cost_path.is_file():
        data["cost_model"] = json.loads(cost_path.read_text(encoding="utf-8"))
    assert data["requested_tool_count"] == 29
    assert len(data["requested_tool_coverage"]) == 29
    assert all(data["requested_tool_coverage"].values())
    ids = {t["id"] for t in data["tools"]}
    assert len(ids) == len(data["tools"])
    assert all(tid in ids for p in data["pipeline"] for tid in p["tools"])
    assert [g["id"] for g in data["gates"]] == ["G0", "G1", "G2", "G3"]
    assert len(data["pipeline"]) == 12
    public_check(json.dumps(data, ensure_ascii=False), "content.json")
    DIST.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dump(DIST / "hub-data.json", data)
    dump(DOWNLOADS / "hub-data.json", data)
    if "cost_model" in data:
        dump(DOWNLOADS / "cost-model.json", data["cost_model"])
    core_path=ROOT/"content-system"/"source.json"
    if not core_path.is_file():
        core_path=DOWNLOADS/"integrated-guide.json"
    canonical_ref=dict(data["meta"].get("canonical_guide", {}))
    if core_path.is_file():
        core=json.loads(core_path.read_text(encoding="utf-8"))
        public_check(json.dumps(core,ensure_ascii=False),"integrated-guide.json")
        dump(DOWNLOADS/"integrated-guide.json",core)
        canonical_ref.update(version=core["version"],source_sha256=hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest(),snapshot_included=True)
    core_md=ROOT/"dist"/"downloads"/"content-system-v7.md"
    if core_md.is_file():
        text=core_md.read_text(encoding="utf-8")
        public_check(text,"integrated-guide.md")
        (DOWNLOADS/"integrated-guide.md").write_text(text,encoding="utf-8")
    blueprint = {
        "schema_version": 1,
        "document_version": data["meta"]["version"],
        "kind": "design_blueprint_not_a_connected_runner",
        "execution_verdict": "not_executed",
        "parent_guide": canonical_ref,
        "defaults": {
            "execute_external": False,
            "paid_generation_enabled": False,
            "external_publication_enabled": False,
            "newsletter_send_enabled": False,
            "coupon_write_enabled": False,
            "budget_usd": 0,
            "default_visibility": "private",
            "max_refine_iterations": 2,
            "heavy_local_concurrency": 1,
        },
        "approval_gates": data["gates"],
        "current_implementation": {
            "planning_selection_0": "implemented_static_audit",
            "source_approval_1": "implemented_static_audit",
            "per_output_release_2": "implemented_static_audit",
            "issue_approval_and_send_3": "not_connected",
            "external_publishing": "not_connected",
            "marketplace_offer_and_coupon": "not_connected",
            "new_model_quality_winner": None,
            "source_model_default": {"model": "gemini-3.8-flash", "scope": "static_code_only_not_database_or_live_call"},
            "voice_profiles": {"ids": ["windows-heami", "gemini-kore"], "scope": "static_code_only_not_database_or_live_call"},
        },
        "stages": data["pipeline"],
        "requested_tool_coverage": data["requested_tool_coverage"],
        "required_records": {
            "AudienceBrief": ["topic", "audience", "problem", "prior_knowledge", "intent", "selected_outputs", "budget"],
            "SourceRecord": ["source_id", "url", "publisher", "collected_at", "version", "content_hash", "rights", "read_scope"],
            "ClaimRecord": ["claim_id", "claim", "source_ids", "evidence_status", "limitations"],
            "ShotSpec": ["shot_id", "purpose", "claim_ids", "source_or_reenactment", "dialogue", "screen_text", "action", "camera", "start_state", "end_state", "rights", "audio_duration", "version"],
            "AssetRecord": ["asset_id", "sha256", "uri", "rights_status", "source_version", "provider", "model", "settings", "approval_scope"],
            "AudioAssetRecord": ["asset_id", "origin_url", "creator", "license_name", "license_version", "license_url", "evidence_hash", "downloaded_at", "allowed_channels", "commercial_use_status", "sync_adaptation_status", "attribution", "performer_consent_ref", "content_id_status", "raw_hash", "mix_hash"],
            "SpeechTiming": ["audio_sha256", "display_script_hash", "pronunciation_text_hash", "actual_duration", "subtitle_sha256", "alignment_model", "qa_evidence", "status"],
            "OfferSnapshot": ["product_id", "product_revision", "product_hash", "canonical_url", "title", "currency", "price", "availability", "campaign_terms", "starts_at", "ends_at", "valid_until", "usage_limit", "issuance_limit", "fetched_at", "terms_hash", "snapshot_hash"],
            "IssueDraft": ["issue_id", "channel", "account_ref", "scheduled_at", "timezone", "source_versions", "source_approval_id", "release_approval_ids", "manifest_hash", "offer_snapshot_hash", "audience_segment", "consent_snapshot", "suppression_snapshot", "frequency_check", "budget", "approval_3"],
            "DeliveryRecord": ["content_id", "asset_hash", "account_ref", "channel", "visibility", "schedule", "approval_id", "idempotency_key", "external_id", "state", "reconciled_at"],
            "ModelEvaluation": ["fixture_id", "model_version", "raw_output_hash", "postprocessed_hash", "critical_failures", "blind_scores", "retries", "elapsed", "resource_usage", "total_cost", "accepted", "human_review"],
            "CostRecord": ["job_id", "route", "period", "started_count", "accepted_count", "model_settings", "rate_version", "actual_token_usage", "image_attempts", "discarded_takes", "billed_native_seconds", "accepted_seconds", "tts_billable_characters", "human_revision_minutes", "blocked_wait_minutes", "usage_value", "cash_charge", "subscription_allocation", "setup_cost_allocation", "currency", "refund", "evidence_status"],
        },
        "record_rules": {
            "required_records_status": "proposed_contracts_not_current_database_schemas",
            "nullable_fields": "Use explicit null for conditions that do not apply; never invent a value to satisfy a schema.",
            "offer_time_semantics": "fetched_at is verification time; valid_until is permitted reuse deadline; starts_at/ends_at are campaign validity. Expired or unverifiable terms suppress commerce CTA.",
            "issue_binding": "An issue binds the exact approved source, release manifests, account, channel, schedule, timezone, consent and optional offer snapshot. Changes require affected approvals to be rechecked.",
            "cost_semantics": "Use all period costs divided by accepted outputs; retain abandoned jobs and discarded takes once. Separate estimated usage value, actual cash charges and human time. Do not double-count subscription credits or common-source costs. Hypothetical examples are not invoices or authorized budgets.",
            "audio_rights": "License, synchronization/adaptation rights, attribution, performer consent and Content ID state are separate checks. A generated or licensed track is not automatically cleared for every channel. Bind subtitles and alignment evidence to the actual audio hash.",
        },
        "delivery_states": ["created", "accepted", "processing", "draft", "private", "scheduled", "published", "failed", "unknown"],
        "failure_rules": [
            "No approval is fabricated by an agent.",
            "A failed video does not invalidate an accepted independent article.",
            "A source change invalidates only dependent claims/assets and affected approvals.",
            "Unknown provider result is reconciled before a retry.",
            "Missing verified offer suppresses commerce CTA and coupon issuance.",
            "YouTube engagement/subscription is not rewarded with coupons.",
            "Private learning material and credentials are excluded from public exports.",
        ],
        "fixture_only_job": {
            "job_id": "example-neutral-001", "is_fixture": True,
            "selected_outputs": ["article", "short_video", "checklist"],
            "source_approval_id": None, "release_approvals": [], "issue_approval_id": None,
            "provider_jobs_submitted": 0, "deliveries_submitted": 0, "coupon_operations": 0,
        },
    }
    dump(DOWNLOADS / "pipeline-blueprint.json", blueprint)
    guide = (SOURCE / "master-guide.md").read_text(encoding="utf-8")
    readme = (SOURCE / "README.md").read_text(encoding="utf-8")
    for name, text in [("master-guide.md", guide), ("README.md", readme)]:
        public_check(text, name)
        (DOWNLOADS / name).write_text(text, encoding="utf-8")
    model_text = "# 도구·모델·자동화·권리 비교\n\n" + data["meta"]["date"] + " 공식 자료 확인. 실제 생성 품질 비교·계정 접근·청구 검증은 미실행.\n\n"
    model_text += table(["도구", "역할/선택", "연결", "제약", "비용", "권리·공식 근거"], [
        [t["name"], t["stage"] + " / " + t["choice"], t["automation"],
         t["reason"] + " " + t["limitations"], t["cost"],
         t["license"] + " " + " · ".join("[" + u["label"] + "](" + u["url"] + ")" for u in t["urls"])]
        for t in data["tools"]])
    model_text += "\n## 사용자 요청 이름의 누락 검사\n\n" + table(["입력 이름", "대응 ID"], data["requested_tool_coverage"].items())
    (DOWNLOADS / "models-and-rights.md").write_text(model_text, encoding="utf-8")
    source_text = "# 콘텐츠 입력 소스 등록부\n\n전체 인터넷을 수집하는 목록이 아니다. 선택한 출처·판본·권리·확보 범위를 기록한다.\n\n"
    source_text += table(["소스", "유형", "수집 경로", "사용 목적", "권리·검증", "공식 URL"], [
        [s["name"], s["type"], s["collection"], s["why"], s["rights"] + " / " + str(s.get("verification", "확인 범위 별도")), s["url"]]
        for s in data["sources"]])
    (DOWNLOADS / "input-sources.md").write_text(source_text, encoding="utf-8")
    for source in sorted((SOURCE / "research").glob("*")):
        if not source.is_file() or source.suffix not in (".md", ".json"):
            continue
        if "PRIVATE" in source.name:
            raise ValueError("Private file in reviewed export source")
        text = source.read_text(encoding="utf-8")
        public_check(text, source.name)
        shutil.copyfile(source, DOWNLOADS / source.name)
    snapshot = """# 현재 구현 정적 확인 요약

2026-10-28의 기존 오피스 코드·README를 대상으로 읽기 전용 확인했다. 이번에 앱 API·테스트·실제 생성·게시를 다시 실행한 것은 아니다.

| 기능 | 확인 상태 |
|---|---|
| 기획 선택⓪ | 코드·API 경로 존재 확인 |
| 원고 승인① | 코드·판본 확인 경로 존재 |
| 출력별 출고②·ZIP | 코드·검사·패키징 경로 존재 |
| v6 기획·패키징·게이트·성과 CSV·교훈 | 코드 존재 확인 |
| 회차③·뉴스레터 전송 | 라벨/설계와 실제 발송 구현을 구분, 미연결 |
| 상품 오퍼 스냅샷·쿠폰·주문 쓰기 | 미연결 |
| 외부 채널 게시 | 미연결 |
| 새 Claude·Eleven·Qwen·영상 제공자 | 확장 제안, 실제 연결·품질 미검증 |

현행 기본 모델은 Gemini, 음성 프로필은 Windows Heami/Gemini Kore다. 성과 Snapshot은 상품 오퍼 스냅샷이 아니다. 개인정보·개인 경로·계정·소스 해시가 담긴 내부 감사 원문은 이 패키지에서 제외했다.
"""
    (DOWNLOADS / "current-implementation.md").write_text(snapshot, encoding="utf-8")
    checklist = """# 변경·배포 전 확인

1. 원본 데이터/문서의 변경 목적·버전·공식 근거를 기록한다.
2. 29개 요청 이름·12단계·⓪①②③ 의미·추가 지출0·미연결 상태를 보존한다.
3. 모델 문서 존재, 계정 사용 가능, 생성 품질, 실제 게시와 성과를 분리한다.
4. 유료 강의·개인학습 원문·개인 원고·계정·키·개인 경로를 제외한다.
5. 해당 출력의 버전·파일 해시·권리·승인·일정·오퍼 변경을 검사한다.
6. 사이트·문서·JSON·ZIP을 다시 생성하고 구조·링크·모바일·키보드·검색·빈 결과·콘솔을 확인한다.
7. 기존 Site ID와 접근 범위를 유지하고 최신 원격 버전과 병합한다.
8. README·OFFICE_INDEX·변경 기록에 결과와 미검증 범위를 남긴다.
"""
    (DOWNLOADS / "update-checklist.md").write_text(checklist, encoding="utf-8")
    export_names = [p.name for p in sorted(DOWNLOADS.iterdir()) if p.is_file() and p.suffix in (".md", ".json") and p.name != "manifest.json"]
    manifest = dict(version=data["meta"]["version"], date=data["meta"]["date"], canonical_reference=canonical_ref,
        scope="Planning documents and public-safe metadata; no original third-party PDFs, private studies, credentials or runtime state",
        files=[dict(name=name, bytes=(DOWNLOADS/name).stat().st_size, sha256=digest(DOWNLOADS/name)) for name in export_names])
    dump(DOWNLOADS / "manifest.json", manifest)
    zip_path = DOWNLOADS / "content-studio-handoff.zip"
    write_archive(zip_path, {name:(DOWNLOADS/name).read_bytes() for name in export_names+["manifest.json"]})
    (DOWNLOADS / "content-studio-handoff.sha256").write_text(digest(zip_path) + "  content-studio-handoff.zip\n", encoding="ascii")
    source_files, source_bytes = export_source(data)
    print(json.dumps(dict(version=data["meta"]["version"], tools=len(data["tools"]),
        requested_tools=29, pipeline_stages=12, ideas=len(data["ideas"]), sources=len(data["sources"]),
        downloaded_original_pdfs=0, exported_documents=len(export_names)+1, zip_bytes=zip_path.stat().st_size,
        editable_source_files=source_files, editable_source_bytes=source_bytes), ensure_ascii=False))

if __name__ == "__main__":
    main()
