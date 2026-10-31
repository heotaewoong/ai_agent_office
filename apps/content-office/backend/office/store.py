from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_UNSET = object()


class WorkflowError(ValueError):
    pass


class UnknownTaskPending(WorkflowError):
    """A guarded output still has an unresolved task for the same source."""


class CostScopeExceeded(WorkflowError):
    """A paid call would exceed its explicit run budget before reaching the provider."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Store:
    def __init__(self, root: Path | str, budget_krw: int = 10000):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "office.sqlite3"
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS versions(job_id TEXT, hash TEXT, packet TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(job_id,hash));
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL, version TEXT NOT NULL, decision TEXT NOT NULL, actor TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, dedup_key TEXT UNIQUE NOT NULL, owner TEXT, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS costs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, reserved_krw INTEGER NOT NULL, actual_krw INTEGER, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ideas(id TEXT PRIMARY KEY, dedup_key TEXT UNIQUE NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_id TEXT NOT NULL, period TEXT NOT NULL, job_id TEXT, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(channel, external_id, period));
                CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, group_key TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES('budget_cap',?)", (str(budget_krw),))

    @contextmanager
    def connection(self, transaction=False):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        try:
            if transaction:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _job(db, job_id):
        row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise WorkflowError("업무를 찾을 수 없습니다")
        return json.loads(row[0])

    @staticmethod
    def _write_job(db, job):
        from .version_history import archive_production
        previous = db.execute("SELECT data FROM jobs WHERE id=?", (job['id'],)).fetchone()
        if previous:
            archive_production(db, json.loads(previous[0]))
        archive_production(db, job)
        job["updated_at"] = now()
        db.execute("UPDATE jobs SET data=?,updated_at=? WHERE id=?", (canonical(job), job["updated_at"], job["id"]))
        return job

    @staticmethod
    def _event(db, kind, data, job_id=None):
        db.execute("INSERT INTO events(job_id,kind,data,created_at) VALUES(?,?,?,?)", (job_id, kind, canonical(data), now()))

    def event(self, kind, data, job_id=None):
        with self.connection() as db:
            self._event(db, kind, data, job_id)

    def setting(self, key, default=None):
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, canonical(value)))

    def save_articles(self, articles):
        with self.connection(transaction=True) as db:
            for article in articles:
                db.execute("INSERT OR REPLACE INTO articles VALUES(?,?,?)", (article["id"], canonical(article), now()))

    def articles_list(self):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM articles ORDER BY updated_at DESC")]

    def article(self, article_id):
        with self.connection() as db:
            r = db.execute("SELECT data FROM articles WHERE id=?", (article_id,)).fetchone()
            if not r:
                raise WorkflowError("기사를 찾을 수 없습니다")
            return json.loads(r[0])

    @staticmethod
    def _validated_brief(brief):
        # briefs.py가 WorkflowError를 이 모듈에서 가져오므로 순환 import를 피해 함수 안에서 불러온다
        from .briefs import normalise_brief
        return normalise_brief(brief)

    def _create_job(self, db, article, brief=None):
        """기존 연결에서 작업을 만들거나 동일 기사 작업을 반환한다. 호출자가 트랜잭션을 소유한다."""
        brief = self._validated_brief(brief)
        for row in db.execute("SELECT data FROM jobs"):
            existing = json.loads(row[0])
            if existing["article"]["id"] == article["id"]:
                return existing
        job = {"id": identifier("job"), "article": article, "title": article.get("editorial_title", article["title"]), "state": "research_ready", "error": None, "source_hash": None, "source_packet": None, "source_approval": None, "release_approval": None, "manifest": None, "selections": {"blog": True, "video": True, "pdf": False, "cards": False}, "brief": brief, "created_at": now(), "updated_at": now()}
        db.execute("INSERT INTO jobs VALUES(?,?,?)", (job["id"], canonical(job), now()))
        self._event(db, "job_created", {"article_id": article["id"], "role": "총괄", "brief_preset": brief["preset"]}, job["id"])
        return job

    def create_job(self, article, brief=None):
        with self.connection(transaction=True) as db:
            return self._create_job(db, article, brief)

    def set_brief(self, job_id, brief, actor, *, expected_hash=_UNSET):
        """작업의 독자 브리프를 바꾼다. 승인은 건드리지 않으며 다음 원고 생성·검수부터 적용된다."""
        if not str(actor or "").strip():
            raise WorkflowError("브리프를 바꾼 담당자가 필요합니다")
        validated = self._validated_brief(brief)
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if expected_hash is not _UNSET and digest(job.get("brief")) != expected_hash:
                raise WorkflowError("다른 화면에서 독자 브리프가 변경되었습니다. 최신 브리프를 불러온 뒤 다시 편집하세요")
            job["brief"] = validated
            self._event(db, "brief_set", {"preset": validated["preset"], "axis": validated["axis"], "actor": actor, "role": "기획", "next_action": "새 원고를 생성하거나 재검수하면 바뀐 브리프가 적용됩니다"}, job_id)
            return self._write_job(db, job)

    def job(self, job_id):
        from .offers import offer_hash
        with self.connection() as db:
            job = self._job(db, job_id)
            if job.get("offer") or "offer_hash" in job:
                job["offer_hash"] = offer_hash(job.get("offer"))
            return job

    def jobs(self, limit=None):
        with self.connection() as db:
            if limit is None:
                rows = db.execute("SELECT data FROM jobs ORDER BY updated_at DESC")
            else:
                rows = db.execute("SELECT data FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,))
            return [json.loads(row[0]) for row in rows]

    def update_job(self, job_id, **values):
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            job.update(values)
            return self._write_job(db, job)

    def save_source(self, job_id, packet, expected_hash=_UNSET, *, expected_offer_hash=_UNSET):
        if not packet.get("title") or not packet.get("body"):
            raise WorkflowError("원고 제목과 본문이 필요합니다")
        from .offers import offer_hash, offer_snapshot, source_version
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if expected_offer_hash is not _UNSET and offer_hash(job.get("offer")) != expected_offer_hash:
                raise WorkflowError("원고를 만드는 동안 상품·쿠폰 조건이 변경되어 옛 결과를 저장하지 않았습니다")
            previous_platforms = (job.get('source_packet') or {}).get('video_platforms')
            if 'video_platforms' not in packet and previous_platforms is not None:
                packet = {**packet, 'video_platforms': previous_platforms, 'video_platform_registry': (job.get('source_packet') or {}).get('video_platform_registry', [])}
            from .video_platforms import selected_platforms
            selected_platforms(packet)
            version = source_version(packet, job.get("offer"))
            if expected_hash is not _UNSET and job["source_hash"] != expected_hash:
                raise WorkflowError("작업 도중 원고 버전이 변경되어 옛 결과를 저장하지 않았습니다")
            if job["source_hash"] == version:
                return job
            recorded = {**packet, "offer_snapshot": offer_snapshot(job["offer"])} if job.get("offer") else packet
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?)", (job_id, version, canonical(recorded), now()))
            job.update(source_hash=version, source_packet=packet, title=packet["title"], state="source_review", source_approval=None, release_approval=None, manifest=None, error=None)
            self._event(db, "source_saved", {"version": version, "role": "편집"}, job_id)
            return self._write_job(db, job)

    def review_source(self, job_id, version, decision, actor, selections=None, *, production_contract=None, external_media_reviewed=False):
        from .offers import require_campaign_packet, require_offer_ready
        if decision not in ("approved", "rejected") or not actor.strip():
            raise WorkflowError("유효한 검토 판정과 검토자가 필요합니다")
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if not version or version != job["source_hash"]:
                raise WorkflowError("원고 버전이 변경되었습니다. 현재 원고를 다시 확인하세요")
            if decision == "approved":
                require_offer_ready(job.get("offer"))
                require_campaign_packet(job.get("source_packet"), job.get("offer"))
            quality = (job["source_packet"] or {}).get("quality", {})
            manual_external = quality.get("status") == "external_review_required"
            if decision == "approved" and manual_external:
                if external_media_reviewed is not True or quality.get("critical"):
                    raise WorkflowError("기존 편집본의 원문·음성·자막을 직접 확인해 주세요")
                from .external_media import validate_packet
                validate_packet(self, job)
            elif decision == "approved" and (quality.get("critical") or quality.get("status") != "passed"):
                raise WorkflowError("중대 오류 또는 미완료 검수가 있어 승인할 수 없습니다")
            if selections is not None:
                updated_selections = {key: bool(selections.get(key, False)) for key in ("blog", "video", "pdf", "cards")}
                if decision == "approved" and not any(updated_selections.values()):
                    raise WorkflowError("제작물을 하나 이상 선택해야 합니다")
                if updated_selections != job["selections"]:
                    job.update(manifest=None, release_approval=None)
                job["selections"] = updated_selections
            if decision == "rejected":
                job["release_approval"] = None
            if decision == "approved" and not any(job["selections"].values()):
                raise WorkflowError("제작물을 하나 이상 선택해야 합니다")
            record = {"id": identifier("approval"), "version": version, "decision": decision, "actor": actor, "selections": job["selections"], "created_at": now()}
            if manual_external:
                record["external_media_reviewed"] = external_media_reviewed is True
                record["review_method"] = "operator_external_media"
            db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)", (record["id"], job_id, "source", version, decision, actor, canonical(record), now()))
            job.update(source_approval=record, state="source_approved" if decision == "approved" else "source_rejected")
            if production_contract is not None:
                if decision != 'approved' or not isinstance(production_contract, str) or len(production_contract) != 64 or any(c not in '0123456789abcdef' for c in production_contract):
                    raise WorkflowError('자동 제작 요청의 판본을 확인해 주세요')
                key=f'produce:{job_id}:{version}:{production_contract}'
                if db.execute("SELECT 1 FROM tasks WHERE kind='produce' AND state='unknown' AND json_extract(payload,'$.job_id')=? AND json_extract(payload,'$.source_hash')=?",(job_id,version)).fetchone():
                    raise WorkflowError('같은 원고의 결과 불명 제작이 있습니다. 결과를 먼저 확인해 주세요')
                if db.execute('SELECT 1 FROM tasks WHERE dedup_key=?',(key,)).fetchone():
                    raise WorkflowError('같은 판본의 제작 요청이 이미 있습니다. 현재 제작 상태를 확인하세요')
                payload={'job_id':job_id,'source_hash':version,'production_contract':production_contract}
                task_id=identifier('task')
                db.execute("INSERT INTO tasks VALUES(?,?,?,'queued',?,NULL,NULL,?,?)",(task_id,'produce',canonical(payload),key,now(),now()))
                job['state']='production_queued'
                self._event(db,'production_queued_after_source_approval',{'task_id':task_id,'source_hash':version,'production_contract':production_contract},job_id)
            self._event(db, "source_" + decision, record, job_id)
            return self._write_job(db, job)

    def register_source_input(self, job_id, text, expected_hash, preserve_original=False):
        from .offers import offer_snapshot, source_version
        if type(preserve_original) is not bool:
            raise WorkflowError("원문 보존 여부는 true 또는 false여야 합니다")
        if preserve_original and (not isinstance(text, str) or not text.strip()):
            raise WorkflowError("원문 보존 모드에는 직접 제공한 Markdown 본문이 필요합니다")
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if job["source_hash"] != expected_hash:
                raise WorkflowError("원문을 등록하는 동안 원고 버전이 변경되었습니다")
            packet = {**(job.get("source_packet") or {"title": job["title"], "body": "공개 원문을 등록했습니다. 근거 정리와 새 원고 생성을 기다리고 있습니다."}), "evidence": [], "source_input_hash": digest(text), "quality": {"status": "unverified", "critical": True, "reviews": []}}
            if preserve_original:
                packet.update(body=text, preserve_original=True)
            else:
                packet.pop("preserve_original", None)
            packet.pop("reference_evidence_ids", None)
            article = {**job["article"], "operator_source_text": text, "preserve_original": preserve_original, "evidence": [], "evidence_source_kind": "operator_supplied_text_pending_extraction"}
            version = source_version(packet, job.get("offer"))
            recorded = {**packet, "offer_snapshot": offer_snapshot(job["offer"])} if job.get("offer") else packet
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?)", (job_id, version, canonical(recorded), now()))
            job.update(article=article, source_hash=version, source_packet=packet, source_approval=None, release_approval=None, manifest=None, state="research_ready", error=None)
            self._event(db, "source_input_saved", {"source_input_hash": digest(text), "version": version, "preserve_original": preserve_original, "role": "연구"}, job_id)
            return self._write_job(db, job)

    def add_draft(self, job_id, draft, *, expected_source_hash=_UNSET):
        """Keep an editorial draft beside the job. It never changes source, approvals or outputs."""
        if not draft.get("title") or not draft.get("body"):
            raise WorkflowError("초안 제목과 본문이 필요합니다")
        identity={"job_id": job_id, "title": draft["title"], "body": draft["body"], "video": draft.get("video")}
        if draft.get('assets'):identity.update(assets=draft['assets'],source_hash_snapshot=draft.get('source_hash_snapshot'))
        draft_id = "draft_" + digest(identity)[:16]
        with self.connection(transaction=True) as db:
            current=self._job(db, job_id)
            if expected_source_hash is not _UNSET and current.get('source_hash')!=expected_source_hash:
                raise WorkflowError('편집 결과를 연결하는 동안 원고 판본이 변경되었습니다')
            row = db.execute("SELECT data FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if row:
                return json.loads(row[0])
            record = {**draft, "id": draft_id, "job_id": job_id, "status": "unapproved_draft", "created_at": now()}
            db.execute("INSERT INTO drafts VALUES(?,?,?,?)", (draft_id, job_id, canonical(record), now()))
            self._event(db, "draft_registered", {"draft_id": draft_id, "title": draft["title"], "role": "편집", "next_action": "초안을 읽고 편집기로 불러와 저장하면 새 원고 버전으로 재검수합니다"}, job_id)
            return record

    def drafts(self, job_id):
        with self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM drafts WHERE job_id=? ORDER BY created_at DESC", (job_id,))]

    def require_source_approval(self, job_id):
        from .offers import require_campaign_packet, require_offer_ready
        job = self.job(job_id)
        require_offer_ready(job.get("offer"))
        require_campaign_packet(job.get("source_packet"), job.get("offer"))
        record = job.get("source_approval") or {}
        if record.get("decision") != "approved" or record.get("version") != job.get("source_hash") or record.get("selections") != job.get("selections"):
            raise WorkflowError("현재 원고 승인①이 필요합니다")
        return job

    def save_article_evidence_if_current(self, job_id, expected_hash, article):
        """Attach job evidence while its source is current; keep operator text out of RSS rows."""
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if job.get('source_hash') != expected_hash:
                raise WorkflowError('조사 중 원문 버전이 변경되었습니다. 현재 원문으로 다시 조사하세요')
            if article.get('id') != job['article'].get('id') or article.get('url') != job['article'].get('url'):
                raise WorkflowError('조사 대상 기사가 변경되었습니다')
            job['article'] = article
            return self._write_job(db, job)

    def save_manifest_if_current(self, job_id, source_hash, selections, manifest):
        from .offers import require_campaign_packet, require_offer_ready
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            require_offer_ready(job.get("offer"))
            require_campaign_packet(job.get("source_packet"), job.get("offer"))
            approval = job.get("source_approval") or {}
            if job["source_hash"] != source_hash or job["selections"] != selections:
                raise WorkflowError("제작 중 원고 버전 또는 제작 선택이 변경되었습니다")
            if approval.get("version") != source_hash or approval.get("decision") != "approved" or approval.get("selections") != selections:
                raise WorkflowError("현재 원고 승인①이 필요합니다")
            if manifest.get("source_hash") != source_hash:
                raise WorkflowError("제작물의 부모 원고 버전이 다릅니다")
            partial = any(status.get('state') != 'completed' for status in manifest.get('output_status', {}).values())
            job.update(manifest=manifest, state="partial_release_review" if partial else "release_review", release_approval=None, error=None)
            self._event(db, "production_partial" if partial else "production_completed", {"source_hash": source_hash, "role": "영상·제작", 'completed_outputs': manifest.get('completed_outputs')}, job_id)
            return self._write_job(db, job)

    def select_thumbnail(self, job_id, artifact_id, expected_manifest_hash, actor):
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            manifest = job.get("manifest")
            approval = job.get("source_approval") or {}
            if not manifest or manifest.get("hash") != expected_manifest_hash or manifest.get("source_hash") != job["source_hash"]:
                raise WorkflowError("썸네일 대상 제작물 버전이 변경되었습니다")
            if approval.get("decision") != "approved" or approval.get("version") != job["source_hash"] or approval.get("selections") != job["selections"]:
                raise WorkflowError("현재 원고 승인①이 필요합니다")
            if artifact_id not in {candidate["id"] for candidate in manifest.get("thumbnail_candidates", [])}:
                raise WorkflowError("현재 제작물의 썸네일 후보가 아닙니다")
            if manifest.get("selected_thumbnail_id") == artifact_id:
                return job
            manifest.setdefault("render_hash", manifest["hash"])
            manifest.update(selected_thumbnail_id=artifact_id, thumbnail_selection_status="selected_by_operator", thumbnail_selection={"actor": actor, "at": now()})
            manifest["hash"] = digest({key: value for key, value in manifest.items() if key != "hash"})
            job.update(manifest=manifest, release_approval=None, state="release_review")
            self._event(db, "thumbnail_selected", {"artifact_id": artifact_id, "actor": actor, "manifest_hash": manifest["hash"]}, job_id)
            return self._write_job(db, job)

    def review_release(self, job_id, manifest_hash, decision, actor, media_reviewed=False, outputs=None, *, private_channel=None):
        from .offers import require_campaign_packet, require_offer_ready
        if decision not in ("approved", "rejected") or not actor.strip():
            raise WorkflowError("유효한 출고 판정과 검토자가 필요합니다")
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if decision == "approved":
                require_offer_ready(job.get("offer"))
                require_campaign_packet(job.get("source_packet"), job.get("offer"))
            manifest = job.get("manifest")
            source_approval = job.get("source_approval") or {}
            if not manifest or manifest.get("hash") != manifest_hash or manifest.get("source_hash") != job["source_hash"]:
                raise WorkflowError("출고 대상 버전이 변경되었습니다")
            if source_approval.get("version") != job["source_hash"] or source_approval.get("decision") != "approved" or source_approval.get("selections") != job["selections"]:
                raise WorkflowError("현재 원고 승인①이 필요합니다")
            requested = {kind for kind, enabled in job['selections'].items() if enabled}
            completed = set(manifest.get('completed_outputs', requested))
            selected = requested if outputs is None else set(outputs)
            if not selected or not selected.issubset(requested) or not selected.issubset(completed):
                raise WorkflowError('완료된 제작물만 출고할 수 있습니다. 미완료 항목을 제외하고 선택하세요')
            if decision == "approved" and 'video' in selected:
                candidates = {candidate["id"] for candidate in manifest.get("thumbnail_candidates", [])}
                if manifest.get("selected_thumbnail_id") not in candidates:
                    raise WorkflowError("썸네일 후보를 비교하고 최종안을 먼저 선택하세요")
                if not media_reviewed:
                    raise WorkflowError("영상·음성·자막을 실제로 검토했다는 확인이 필요합니다")
            record = {"version": manifest_hash, "decision": decision, "actor": actor, "created_at": now(), "outputs": sorted(selected), "target": "manual-handoff", "media_reviewed": bool(media_reviewed), "external_published": False}
            if private_channel is not None:
                if decision!='approved' or 'video' not in selected or private_channel.get('key') not in ('youtube_main_ko','youtube_english'):
                    raise WorkflowError('검토한 영상의 출고 승인과 YouTube 대상이 필요합니다')
                key=f'private-delivery:{job_id}:{manifest_hash}:{private_channel["key"]}'
                if db.execute('SELECT 1 FROM tasks WHERE dedup_key=?',(key,)).fetchone():
                    raise WorkflowError('같은 제작물의 전송 요청이 이미 있습니다. 전송 기록을 먼저 확인해 주세요')
                record['private_delivery']={'channel_key':private_channel['key'],'channel_hash':digest(private_channel),'privacy':'private'}
                payload={'job_id':job_id,'source_hash':job['source_hash'],'manifest_hash':manifest_hash,'release_hash':digest(record),'channel_key':private_channel['key'],'channel_hash':digest(private_channel)}
                db.execute("INSERT INTO tasks VALUES(?,?,?,'queued',?,NULL,NULL,?,?)",(identifier('task'),'private_delivery',canonical(payload),key,now(),now()))
            db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)", (identifier("approval"), job_id, "release", manifest_hash, decision, actor, canonical(record), now()))
            self._event(db, "release_" + decision, record, job_id)
            job.update(release_approval=record, state="release_approved" if decision == "approved" else "release_review")
            job = self._write_job(db, job)
        if decision == "approved":
            # 승인② 기록이 확정된 뒤(트랜잭션 밖) 뉴스레터 초안 회차를 자동으로 만든다. 초안일 뿐 승인③은 사람이 한다.
            from .newsletter import auto_build_issue
            auto_build_issue(self, job_id, actor=actor)
        return job

    def enqueue(self, kind, payload, key, *, guard_unknown_scope=False):
        """Queue work once per key. A *failed* earlier attempt does not swallow a new explicit request:
        the operator's next click queues a fresh task (key suffixed with the attempt number). Queued,
        running, completed and unknown attempts are returned as they are; unknown stays until reconciled."""
        with self.connection(transaction=True) as db:
            if guard_unknown_scope and db.execute(
                "SELECT 1 FROM tasks WHERE kind=? AND json_extract(payload,'$.job_id') IS ? AND json_extract(payload,'$.source_hash') IS ? AND state='unknown' LIMIT 1",
                (kind, payload.get("job_id"), payload.get("source_hash")),
            ).fetchone():
                raise UnknownTaskPending("같은 원고의 이 제작 유형에 결과 불명 작업이 있습니다. 대사로 결과를 확인하기 전에는 새 요청을 만들지 않습니다")
            rows = db.execute("SELECT * FROM tasks WHERE dedup_key=? OR dedup_key LIKE ? ORDER BY created_at DESC, dedup_key DESC", (key, key + "#%")).fetchall()
            if rows and rows[0]["state"] != "failed":
                return self._task(rows[0])
            dedup_key = key if not rows else f"{key}#{len(rows) + 1}"
            task_id = identifier("task")
            db.execute("INSERT INTO tasks VALUES(?,?,?,'queued',?,NULL,NULL,?,?)", (task_id, kind, canonical(payload), dedup_key, now(), now()))
            return self._task(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    @staticmethod
    def _task(row):
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def claim(self, owner):
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE tasks SET state='running',owner=?,updated_at=? WHERE id=?", (owner, now(), row["id"]))
            return self._task(db.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone())

    def task(self, task_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise WorkflowError("작업을 찾을 수 없습니다")
            return self._task(row)

    def tasks(self, job_id=None):
        with self.connection() as db:
            if job_id:
                rows = db.execute("SELECT * FROM tasks WHERE json_extract(payload,'$.job_id')=? ORDER BY created_at DESC LIMIT 100", (job_id,))
            else:
                rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100")
            return [self._task(row) for row in rows]

    def task_activity(self, kinds):
        """공간 상태용 종류별 1건: 실행 중 우선, 그 외 최신 기록. 본문은 읽지 않는다."""
        kinds = tuple(dict.fromkeys(kinds))
        if not kinds:
            return []
        placeholders = ",".join("?" for _ in kinds)
        with self.connection() as db:
            rows = db.execute(f"""
                WITH activity AS (
                    SELECT id,kind,state,created_at,updated_at,
                           ROW_NUMBER() OVER (PARTITION BY kind ORDER BY
                               CASE WHEN state IN ('running','claimed') THEN 0 ELSE 1 END,
                               created_at DESC,id DESC) AS position
                    FROM tasks WHERE kind IN ({placeholders})
                )
                SELECT id,kind,state,created_at,updated_at FROM activity
                WHERE position=1 ORDER BY created_at DESC,id DESC
            """, kinds)
            return [dict(row) for row in rows]

    def finished_task_count(self, job_id, kind, source_hash):
        """재요청 키의 기존 종료·결과불명 집계에는 화면 이력의 100개 제한을 적용하지 않는다."""
        with self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM tasks WHERE kind=? AND json_extract(payload,'$.job_id')=? AND json_extract(payload,'$.source_hash') IS ? AND state NOT IN ('queued','running')", (kind, job_id, source_hash)).fetchone()[0]

    def finish_task(self, task_id, owner, result, state="completed"):
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["owner"] != owner or row["state"] != "running":
                raise WorkflowError("작업 소유자가 다르거나 이미 종료된 작업입니다")
            db.execute("UPDATE tasks SET state=?,result=?,updated_at=? WHERE id=?", (state, canonical(result), now(), task_id))

    def events(self, job_id=None, limit=100):
        with self.connection() as db:
            if job_id:
                rows = db.execute("SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, limit))
            else:
                rows = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
            return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    # --- 기획 선택⓪ · 성과 스냅샷 · 교훈 (AI 콘텐츠 에이전트 v6)
    @staticmethod
    def _idea_key(card):
        title = " ".join(str(card.get("title", "")).lower().split())
        return digest({"title": title, "source_url": card.get("source_url", "")})

    def save_idea(self, card, *, parent_job_id=None, parent_source_hash=None, parent_quiz_hash=None):
        if not str(card.get("title", "")).strip():
            raise WorkflowError("기획 제목이 필요합니다")
        key = self._idea_key(card)
        with self.connection(transaction=True) as db:
            if parent_job_id is not None:
                parent = self._job(db, parent_job_id)
                if parent.get('source_hash') != parent_source_hash or digest(parent.get('quiz') or {}) != parent_quiz_hash:
                    raise WorkflowError('기획 후보를 저장하는 동안 부모 원고/문항이 변경되었습니다')
            row = db.execute("SELECT data FROM ideas WHERE dedup_key=?", (key,)).fetchone()
            if row:
                stored = json.loads(row[0])
                if parent_job_id is not None:
                    return stored  # Preserve any prior human edits/selection on a feedback retry.
                merged = {**stored, **card, "id": stored["id"], "state": stored.get("state", "candidate")}
                for field in ("selected_by", "selected_at"):
                    if field in stored:
                        merged[field] = stored[field]
                db.execute("UPDATE ideas SET data=?, updated_at=? WHERE id=?", (canonical(merged), now(), merged["id"]))
                return merged
            idea = {**card, "id": identifier("idea"), "state": "candidate"}
            db.execute("INSERT INTO ideas VALUES(?,?,?,?,?,?)", (idea["id"], key, "candidate", canonical(idea), now(), now()))
            self._event(db, "idea_saved", {"idea_id": idea["id"], "title": idea["title"]})
            return idea

    def ideas(self, state=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM ideas WHERE (? IS NULL OR state=?) ORDER BY created_at", (state, state)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def select_idea(self, idea_id, actor):
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if not row:
                raise WorkflowError("기획을 찾을 수 없습니다")
            idea = json.loads(row[0])
            if "blocked" not in idea:
                raise WorkflowError("점수를 매기지 않은 기획은 선택할 수 없습니다")
            if idea.get("blocked"):
                raise WorkflowError("정책·근거 검사에서 막힌 기획은 선택할 수 없습니다")
            idea.update(state="selected", selected_by=actor, selected_at=now())
            db.execute("UPDATE ideas SET state='selected', data=?, updated_at=? WHERE id=?", (canonical(idea), now(), idea_id))
            self._event(db, "idea_selected", {"idea_id": idea_id, "actor": actor})
            return idea

    # --- 독자 질문 수집(개인정보 없이 출처·채널 키·본문만). 묶음 수는 읽을 때 센다.
    @staticmethod
    def _question_rows(db):
        rows = db.execute("SELECT data FROM questions ORDER BY created_at DESC, rowid DESC").fetchall()
        items = [json.loads(r[0]) for r in rows]
        counts = {}
        for item in items:
            counts[item["group_key"]] = counts.get(item["group_key"], 0) + 1
        return [{**item, "count": counts[item["group_key"]]} for item in items]

    def save_question(self, row):
        question = {"id": identifier("q"), "source": row["source"], "text": row["text"], "channel_key": row.get("channel_key"), "created_at": now(), "group_key": row["group_key"], "state": "new"}
        with self.connection(transaction=True) as db:
            db.execute("INSERT INTO questions VALUES(?,?,?,?,?)", (question["id"], question["group_key"], "new", canonical(question), question["created_at"]))
            return next(q for q in self._question_rows(db) if q["id"] == question["id"])

    def questions(self):
        with self.connection() as db:
            return self._question_rows(db)

    def question(self, question_id):
        with self.connection() as db:
            return next((q for q in self._question_rows(db) if q["id"] == question_id), None)

    def mark_questions_converted(self, group_key, idea_id):
        with self.connection(transaction=True) as db:
            for row in db.execute("SELECT data FROM questions WHERE group_key=?", (group_key,)).fetchall():
                question = {**json.loads(row[0]), "state": "converted", "idea_id": idea_id}
                db.execute("UPDATE questions SET state='converted', data=? WHERE id=?", (canonical(question), question["id"]))

    @staticmethod
    def _snapshot(row):
        return {"id": row["id"], "channel": row["channel"], "external_id": row["external_id"], "period": row["period"], "job_id": row["job_id"], "metrics": json.loads(row["data"])}

    def save_snapshot(self, channel, external_id, period, metrics, job_id=None):
        if period not in ("24h", "7d", "28d"):
            raise WorkflowError("성과 측정 구간은 24h·7d·28d 중 하나입니다")
        with self.connection(transaction=True) as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?) ON CONFLICT(channel, external_id, period) DO UPDATE SET data=excluded.data, job_id=excluded.job_id, created_at=excluded.created_at",
                       (identifier("snap"), channel, external_id, period, job_id, canonical(metrics), now()))
            row = db.execute("SELECT * FROM snapshots WHERE channel=? AND external_id=? AND period=?", (channel, external_id, period)).fetchone()
            return self._snapshot(row)

    def snapshots(self, channel=None):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM snapshots WHERE (? IS NULL OR channel=?) ORDER BY created_at", (channel, channel)).fetchall()
        return [self._snapshot(r) for r in rows]

    def add_lesson(self, lesson):
        record = {**lesson, "id": identifier("lesson"), "state": "proposed"}
        snapshot_id = (record.get("evidence") or {}).get("snapshot_id")
        with self.connection(transaction=True) as db:
            if snapshot_id:
                for (data,) in db.execute("SELECT data FROM lessons ORDER BY created_at").fetchall():
                    old = json.loads(data)
                    if old.get("kind") == record.get("kind") and (old.get("evidence") or {}).get("snapshot_id") == snapshot_id:
                        return old
            db.execute("INSERT INTO lessons VALUES(?,?,?,?,?)", (record["id"], "proposed", canonical(record), now(), now()))
            self._event(db, "lesson_proposed", {"lesson_id": record["id"], "kind": record.get("kind")})
        return record

    def review_lesson(self, lesson_id, decision, actor):
        if decision not in ("approved", "rejected"):
            raise WorkflowError("교훈 검토는 approved 또는 rejected입니다")
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT data FROM lessons WHERE id=?", (lesson_id,)).fetchone()
            if not row:
                raise WorkflowError("교훈을 찾을 수 없습니다")
            record = {**json.loads(row[0]), "state": decision, "reviewed_by": actor, "reviewed_at": now()}
            db.execute("UPDATE lessons SET state=?, data=?, updated_at=? WHERE id=?", (decision, canonical(record), now(), lesson_id))
            self._event(db, "lesson_reviewed", {"lesson_id": lesson_id, "decision": decision, "actor": actor})
            return record

    def lessons(self, state=None):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM lessons WHERE (? IS NULL OR state=?) ORDER BY created_at", (state, state)).fetchall()
        return [json.loads(r[0]) for r in rows]

    @staticmethod
    def _budget(db):
        cap = int(db.execute("SELECT value FROM settings WHERE key='budget_cap'").fetchone()[0])
        reserved = db.execute("SELECT COALESCE(SUM(reserved_krw),0) FROM costs WHERE state IN ('reserved','unknown')").fetchone()[0]
        spent = db.execute("SELECT COALESCE(SUM(actual_krw),0) FROM costs WHERE state='settled'").fetchone()[0]
        return {"cap_krw": cap, "spent_krw": spent, "reserved_krw": reserved, "remaining_krw": cap - reserved - spent, "overrun_krw": max(0, spent + reserved - cap), "cost_status": "provider_usage_estimate_pending_invoice", "fx_note": "예산 예약 기준 1 USD = 2,000 KRW 가정; 시장 환율 아님", "pricing_as_of": "2026-10-26"}

    def budget(self):
        with self.connection() as db:
            return self._budget(db)

    @staticmethod
    def _job_budget(db, job_id):
        row = db.execute("SELECT value FROM settings WHERE key=?", ("job_budget:" + job_id,)).fetchone()
        configuration = json.loads(row[0]) if row else None
        cap = configuration["cap_krw"] if configuration else None
        totals = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN state='settled' THEN actual_krw ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state IN ('reserved','unknown') THEN reserved_krw ELSE 0 END),0) "
            "FROM costs WHERE json_extract(data,'$.job_id')=?", (job_id,)).fetchone()
        spent, reserved = totals
        return {"job_id": job_id, "cap_krw": cap, "spent_krw": spent, "reserved_krw": reserved,
                "remaining_krw": cap - spent - reserved if cap is not None else None,
                "overrun_krw": max(0, spent + reserved - cap) if cap is not None else 0,
                "hash": digest({"job_id": job_id, "configuration": configuration}),
                "configured_by": configuration.get("configured_by") if configuration else None,
                "configured_at": configuration.get("configured_at") if configuration else None}

    def get_job_budget(self, job_id):
        with self.connection() as db:
            self._job(db, job_id)
            return self._job_budget(db, job_id)

    def set_job_budget(self, job_id, cap_krw, actor, *, expected_hash):
        if type(cap_krw) is not int or cap_krw <= 0:
            raise WorkflowError("업무 예산 한도는 양의 정수여야 합니다")
        if not isinstance(actor, str) or not actor.strip():
            raise WorkflowError("업무 예산을 설정한 담당자가 필요합니다")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
            raise WorkflowError("현재 업무 예산의 hash가 필요합니다")
        with self.connection(transaction=True) as db:
            self._job(db, job_id)
            current = self._job_budget(db, job_id)
            if expected_hash != current["hash"]:
                raise WorkflowError("업무 예산 설정이 변경되었습니다. 최신 한도를 불러온 뒤 다시 설정하세요")
            if cap_krw > self._budget(db)["cap_krw"]:
                raise WorkflowError("업무 예산 한도는 전체 예산 한도를 넘을 수 없습니다")
            configuration = {"cap_krw": cap_krw, "configured_by": actor.strip()[:120], "configured_at": now()}
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", ("job_budget:" + job_id, canonical(configuration)))
            self._event(db, "job_budget_set", {**configuration, "previous_cap_krw": current["cap_krw"]}, job_id)
            return self._job_budget(db, job_id)

    @staticmethod
    def _cost_scope_budget(db, scope):
        if (not isinstance(scope, dict) or not isinstance(scope.get("id"), str) or not scope["id"]
                or len(scope["id"]) > 200 or type(scope.get("cap_krw")) is not int or scope["cap_krw"] <= 0):
            raise WorkflowError("실행 비용 범위와 양의 정수 한도가 필요합니다")
        spent, reserved = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN state='settled' THEN actual_krw ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state IN ('reserved','unknown') THEN reserved_krw ELSE 0 END),0) "
            "FROM costs WHERE json_extract(data,'$.cost_scope_id')=?", (scope["id"],)).fetchone()
        return {"scope_id": scope["id"], "cap_krw": scope["cap_krw"], "spent_krw": spent,
                "reserved_krw": reserved, "remaining_krw": scope["cap_krw"] - spent - reserved}

    def cost_scope_budget(self, scope):
        with self.connection() as db:
            return self._cost_scope_budget(db, scope)

    def reserve_cost(self, kind, maximum_krw, data, *, scope=None):
        if not math.isfinite(maximum_krw) or maximum_krw < 0:
            raise WorkflowError("잘못된 비용 한도입니다")
        maximum = math.ceil(maximum_krw)
        with self.connection(transaction=True) as db:
            if data.get("cache_key"):
                for row in db.execute("SELECT data FROM costs WHERE state IN ('reserved','unknown')"):
                    if json.loads(row[0]).get("cache_key") == data["cache_key"]:
                        raise WorkflowError("같은 모델 호출이 진행 중이거나 결과 불명입니다. 먼저 비용·결과 대사가 필요합니다")
            if maximum > self._budget(db)["remaining_krw"]:
                raise WorkflowError("예산 한도를 초과하여 호출을 보류합니다")
            if data.get("job_id"):
                job_budget = self._job_budget(db, data["job_id"])
                if job_budget["cap_krw"] is not None and maximum > job_budget["remaining_krw"]:
                    raise WorkflowError(f"이 업무의 합산 예산 {job_budget['cap_krw']:,}원 한도를 초과하여 호출을 보류합니다")
            if scope is not None:
                scope_budget = self._cost_scope_budget(db, scope)
                if maximum > scope_budget["remaining_krw"]:
                    raise CostScopeExceeded(f"이번 실행의 비용 상한({scope_budget['cap_krw']:,}원)을 넘는 최대 예약이 필요하여 호출을 보류합니다")
                data = {**data, "cost_scope_id": scope["id"], "cost_scope_cap_krw": scope["cap_krw"]}
            cost_id = identifier("cost")
            db.execute("INSERT INTO costs VALUES(?,?,'reserved',?,NULL,?,?,?)", (cost_id, kind, maximum, canonical(data), now(), now()))
            return {"id": cost_id, "reserved_krw": maximum}

    def settle_cost(self, cost_id, actual_krw, usage):
        if not math.isfinite(actual_krw) or actual_krw < 0:
            raise WorkflowError("잘못된 정산 금액입니다")
        with self.connection(transaction=True) as db:
            row = db.execute("SELECT * FROM costs WHERE id=?", (cost_id,)).fetchone()
            if not row or row["state"] == "settled":
                raise WorkflowError("없는 예약이거나 이미 정산했습니다")
            data = json.loads(row["data"])
            data["usage"] = usage
            if math.ceil(actual_krw) > row["reserved_krw"]:
                data["reservation_overrun"] = math.ceil(actual_krw) - row["reserved_krw"]
                self._event(db, "cost_exceeded_reservation", {"cost_id": cost_id, "actual_krw": math.ceil(actual_krw), "reserved_krw": row["reserved_krw"], "requires_reconciliation": True})
            db.execute("UPDATE costs SET state='settled',actual_krw=?,data=?,updated_at=? WHERE id=?", (math.ceil(actual_krw), canonical(data), now(), cost_id))

    def unknown_cost(self, cost_id, reason):
        with self.connection(transaction=True) as db:
            db.execute("UPDATE costs SET state='unknown',updated_at=? WHERE id=? AND state='reserved'", (now(), cost_id))
            self._event(db, "cost_unknown", {"cost_id": cost_id, "reason": reason})

    def cache_get(self, key):
        with self.connection() as db:
            row = db.execute("SELECT data FROM cache WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def cache_put(self, key, value):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, canonical(value), now()))

    # Campaign edits create a new reviewed content version; they never issue a store coupon.
    def _replace_offer(self, db, job, offer, actor):
        from .offers import campaign_packet, offer_hash, offer_snapshot, source_version
        if offer is None:
            job.pop("offer", None)
        else:
            job["offer"] = {**offer, "captured_at": now(), "actor": actor}
        job["offer_hash"] = offer_hash(offer)
        packet = job.get("source_packet")
        if packet:
            if offer is None:
                packet = campaign_packet(packet, None)
            packet = {**packet, "quality": {"status": "unverified", "critical": False, "reviews": [], "refine_count": 0}}
            version = source_version(packet, offer)
            recorded = {**packet, "offer_snapshot": offer_snapshot(offer)}
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?)", (job["id"], version, canonical(recorded), now()))
            job.update(source_packet=packet, source_hash=version, source_approval=None, release_approval=None, manifest=None, state="source_review", error=None)
            self._event(db, "offer_content_invalidated", {"source_hash": version, "actor": actor, "next_action": "상품·쿠폰이 바뀌었습니다. 현재 원고와 영상 CTA를 재검수하고 승인①부터 다시 진행하세요"}, job["id"])
        self._event(db, "offer_set" if offer else "offer_cleared", {"offer_hash": job["offer_hash"], "actor": actor, "role": "마케팅", "store_changed": False}, job["id"])
        return self._write_job(db, job)

    def set_offer(self, job_id, offer, actor, *, expected_hash=_UNSET):
        from .offers import normalise_offer, offer_hash
        validated = normalise_offer(offer, actor)
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            current_hash = offer_hash(job.get("offer"))
            if expected_hash is not _UNSET and current_hash != expected_hash:
                raise WorkflowError("다른 화면에서 상품·쿠폰이 변경되었습니다. 최신 작업을 불러온 뒤 다시 편집하세요")
            if current_hash == offer_hash(validated):
                return {**job, "offer_hash": current_hash}
            return self._replace_offer(db, job, validated, actor)

    def clear_offer(self, job_id, actor, *, expected_hash=_UNSET):
        from .offers import offer_hash
        if not str(actor or "").strip():
            raise WorkflowError("오퍼를 바꾼 담당자가 필요합니다")
        with self.connection(transaction=True) as db:
            job = self._job(db, job_id)
            if expected_hash is not _UNSET and offer_hash(job.get("offer")) != expected_hash:
                raise WorkflowError("다른 화면에서 상품·쿠폰이 변경되었습니다. 최신 작업을 불러온 뒤 다시 편집하세요")
            if not job.get("offer"):
                return {**job, "offer_hash": None}
            return self._replace_offer(db, job, None, actor)
