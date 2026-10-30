"""Free real stock footage from Pexels for approved video scenes. No paid call, no paid fallback.

Protocol (official docs, checked 2026-10-30 via search snapshot; direct fetch was blocked on the
operator PC by a TLS interception): https://www.pexels.com/api/documentation/
  GET https://api.pexels.com/videos/search?query=&orientation=portrait&size=medium&per_page=
  header ``Authorization: <key>`` (raw key, no "Bearer"); response ``videos[]`` with ``url``,
  ``user{name,url}`` and ``video_files[]{id,quality,file_type,width,height,link}``.
  Default limit 200 requests/hour, 20,000/month; HTTP 429 when exceeded.
License: https://www.pexels.com/license/ - free for commercial use, modification allowed,
attribution not required but appreciated; do not sell/redistribute unaltered copies or imply
endorsement by people/brands shown. API guidelines ask apps to show Pexels as the source and
credit the creator when possible, so every clip keeps a receipt and the description credits it.

The operator supplies PEXELS_API_KEY through the runtime environment only; it is never written
to receipts, events, exports, or the repository.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

import requests

from .speech_provider import _hash, _json, _lock
from .store import Store, WorkflowError, digest, now

API_URL = "https://api.pexels.com/videos/search"
DOCS_URL = "https://www.pexels.com/api/documentation/"
LICENSE_URL = "https://www.pexels.com/license/"
CONTRACT = "pexels-stock-v1"
PER_PAGE = 15
MIN_WIDTH = 720
MAX_VIDEO_BYTES = 60_000_000
MAX_DOWNLOADS_PER_JOB = 8
GENERIC_QUERY = "office desk laptop"
ALLOWED_HOSTS = ("pexels.com", "player.vimeo.com")
STOPWORDS = {"a", "an", "the", "on", "of", "in", "with", "and", "at", "to", "for", "by", "from", "into", "is", "are"}
# Small deterministic Korean -> English map for scripts approved before the `footage` field existed.
KEYWORDS = {
    "노트북": "laptop", "컴퓨터": "computer", "모니터": "monitor", "키보드": "keyboard", "마우스": "computer mouse",
    "스마트폰": "smartphone", "휴대폰": "smartphone", "핸드폰": "smartphone", "태블릿": "tablet",
    "서류": "documents", "문서": "documents", "보고서": "report papers", "계약서": "contract signing", "영수증": "receipt",
    "책상": "desk", "사무실": "office", "회의실": "meeting room", "회의": "meeting", "메모": "notes", "포스트잇": "sticky notes",
    "화이트보드": "whiteboard", "체크리스트": "checklist", "달력": "calendar", "캘린더": "calendar", "일정": "planner",
    "노트": "notebook", "공책": "notebook", "책": "books", "도서관": "library", "공부": "studying", "학생": "student",
    "수업": "classroom", "강의": "lecture", "교실": "classroom", "시험": "exam", "펜": "pen", "연필": "pencil",
    "손": "hands", "커피": "coffee", "시계": "clock", "차트": "chart", "그래프": "chart", "데이터": "data",
    "서버": "server room", "코드": "coding", "코딩": "coding", "프로그래밍": "programming", "개발자": "programmer",
    "팀": "team", "동료": "coworkers", "대화": "conversation", "전화": "phone call", "이메일": "email", "메일": "email",
    "계산기": "calculator", "돈": "money", "창문": "window", "도시": "city", "거리": "street", "아침": "morning",
    "밤": "night", "집": "home", "카페": "cafe", "로봇": "robot", "기술": "technology", "네트워크": "network",
    "읽기": "reading", "독서": "reading", "글쓰기": "writing", "타이핑": "typing", "상자": "boxes", "택배": "packages",
    "창고": "warehouse", "공장": "factory", "고객": "customer", "상담": "customer support", "아이디어": "brainstorming",
    "계획": "planning", "검색": "searching", "학습": "learning", "업무": "work", "작업": "work",
}
PARTICLES = ("", "을", "를", "이", "가", "은", "는", "에", "의", "도", "로", "과", "와", "만", "에서", "으로", "에게",
             "처럼", "까지", "부터", "이나", "나", "들", "들이", "들을", "하는", "하기", "한다", "해요", "하며", "하고")


class StockFootageUnavailable(WorkflowError):
    """This scene keeps its still picture; nothing paid is called instead."""


def _words(text):
    words = [w for w in re.sub(r"[^a-z0-9 -]+", " ", str(text).lower()).split() if w.strip("-") and w not in STOPWORDS]
    return " ".join(words[:4])


def footage_query(scene):
    """English search words: approved `footage` field, else mapped Korean nouns, else an ASCII caption, else generic."""
    query = _words(scene.get("footage", "")) if isinstance(scene.get("footage"), str) else ""
    if query:
        return query
    found = []
    for token in re.findall(r"[가-힣]+", " ".join(str(scene.get(key, "")) for key in ("visual", "caption"))):
        for key, english in KEYWORDS.items():
            if token.startswith(key) and token[len(key):] in PARTICLES:
                if not set(english.split()) <= set(" ".join(found).split()):
                    found.append(english)
                break
    query = _words(" ".join(found[:3]))
    if query:
        return query
    caption = str(scene.get("caption", ""))
    if re.search(r"[A-Za-z]", caption) and not re.search(r"[가-힣]", caption):
        query = _words(caption)
    return query or GENERIC_QUERY


def _allowed_link(link):
    if not isinstance(link, str):
        return False
    parts = urlsplit(link)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS)


def choose_file(video):
    """A portrait MP4 at least 720 wide; exactly 1080x1920 first, then the closest width to 1080."""
    files = video.get("video_files") if isinstance(video, dict) else None
    if not isinstance(files, list):
        return None
    usable = []
    for item in files:
        if not isinstance(item, dict):
            continue
        width, height = item.get("width"), item.get("height")
        if type(width) is not int or type(height) is not int or width < MIN_WIDTH or height <= width:
            continue
        if item.get("file_type") != "video/mp4" or not _allowed_link(item.get("link")):
            continue
        usable.append(item)
    if not usable:
        return None
    return min(usable, key=lambda f: ((f["width"], f["height"]) != (1080, 1920), abs(f["width"] - 1080), f["width"]))


def stock_profile_config(*, job_id, source_hash, queries):
    if not job_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash or ""):
        raise WorkflowError("실사 영상 프로필에는 업무와 승인 원고 버전이 필요합니다")
    return {"provider": "pexels", "endpoint": API_URL, "orientation": "portrait", "size": "medium", "per_page": PER_PAGE,
            "min_width": MIN_WIDTH, "max_bytes": MAX_VIDEO_BYTES, "max_downloads_per_job": MAX_DOWNLOADS_PER_JOB,
            "queries": list(queries), "job_id": job_id, "source_hash": source_hash, "license_url": LICENSE_URL,
            "paid": False, "contract": CONTRACT}


class StockFootage:
    def __init__(self, store: Store, *, job_id, session=None, probe=None):
        self.store, self.job_id = store, job_id
        self.session = session or requests
        self._probe = probe
        source = store.require_source_approval(job_id)
        self.source_hash = source["source_hash"]
        scenes = source["source_packet"].get("video", {}).get("scenes", [])
        queries = [footage_query(scene) if isinstance(scene, dict) else GENERIC_QUERY for scene in scenes]
        self._config_json = json.dumps(stock_profile_config(job_id=job_id, source_hash=self.source_hash, queries=queries), ensure_ascii=False, sort_keys=True)
        self.assets = store.root / "stock-assets"

    @property
    def config(self):
        return json.loads(self._config_json)

    @property
    def cache_key(self):
        return "pexels-stock:" + digest(self.config)

    @property
    def asset_cache_key(self):
        return "pexels-stock-asset:" + digest({k: self.config[k] for k in ("provider", "orientation", "size", "per_page", "min_width", "contract")})

    def probe(self, path):
        if self._probe is not None:
            return self._probe(path)
        from .media import probe
        return probe(path)

    def _unavailable(self, scene_index, message, query=None):
        self.store.event("stock_footage_unavailable", {"scene": scene_index + 1, "query": query, "reason": message[:200],
                                                       "fallback": "still_scene", "paid_call_made": False}, self.job_id)
        raise StockFootageUnavailable(message)

    def _authorized(self, scene_index):
        job = self.store.require_source_approval(self.job_id)
        if job.get("selections", {}).get("video") is not True:
            raise WorkflowError("영상 제작 선택과 승인이 있어야 실사 영상을 받을 수 있습니다")
        if job["source_hash"] != self.source_hash:
            raise WorkflowError("원고 버전이 변경되어 실사 영상 선택이 무효입니다")
        scenes = job["source_packet"].get("video", {}).get("scenes", [])
        if not (isinstance(scene_index, int) and 0 <= scene_index < len(scenes)):
            raise WorkflowError("승인된 장면 번호만 실사 영상을 받을 수 있습니다")

    def _out(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or path.suffix.lower() != ".mp4":
            raise WorkflowError("실사 영상 경로는 앱 상태 폴더 안의 MP4 파일이어야 합니다")
        return path

    def _downloads(self):
        return sum(1 for event in self.store.events(self.job_id, limit=5000) if event["kind"] == "stock_footage_downloaded")

    def _search(self, scene_index, query):
        try:
            response = self.session.get(API_URL, params={"query": query, "orientation": "portrait", "size": "medium", "per_page": PER_PAGE},
                                        headers={"Authorization": os.environ["PEXELS_API_KEY"]}, timeout=(10, 30))
        except requests.RequestException:
            self._unavailable(scene_index, "Pexels 검색에 연결하지 못했습니다. 이 장면은 정지 화면으로 만듭니다", query)
        if response.status_code != 200:
            self._unavailable(scene_index, f"Pexels 검색 HTTP {response.status_code}. 이 장면은 정지 화면으로 만듭니다", query)
        try:
            videos = response.json().get("videos")
            if not isinstance(videos, list):
                raise ValueError("videos")
        except (ValueError, TypeError, AttributeError):
            self._unavailable(scene_index, "Pexels 검색 응답을 읽지 못했습니다", query)
        return videos

    def _download(self, scene_index, query, link, target):
        partial = target.with_name(target.stem + ".partial.mp4")
        try:
            try:
                response = self.session.get(link, timeout=(10, 120), stream=True)
            except requests.RequestException:
                self._unavailable(scene_index, "Pexels 영상 파일을 내려받지 못했습니다", query)
            try:
                if response.status_code != 200:
                    self._unavailable(scene_index, f"Pexels 영상 파일 HTTP {response.status_code}", query)
                declared = str((response.headers or {}).get("Content-Length", "") or "")
                if declared.isdigit() and int(declared) > MAX_VIDEO_BYTES:
                    self._unavailable(scene_index, f"실사 영상 파일 크기가 상한 {MAX_VIDEO_BYTES // 1_000_000}MB를 넘습니다", query)
                size = 0
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        size += len(chunk)
                        if size > MAX_VIDEO_BYTES:
                            break
                        handle.write(chunk)
            except requests.RequestException:
                self._unavailable(scene_index, "Pexels 영상 파일 전송이 중단됐습니다", query)
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
            if size > MAX_VIDEO_BYTES:
                self._unavailable(scene_index, f"실사 영상 파일 크기가 상한 {MAX_VIDEO_BYTES // 1_000_000}MB를 넘습니다", query)
            with partial.open("rb") as handle:
                head = handle.read(12)
            if head[4:8] != b"ftyp":
                self._unavailable(scene_index, "받은 파일이 MP4 영상 형식이 아닙니다", query)
            try:
                info = self.probe(partial)
            except WorkflowError:
                self._unavailable(scene_index, "ffprobe로 받은 영상을 확인하지 못했습니다", query)
            stream = next((s for s in (info or {}).get("streams", []) if s.get("codec_type") == "video"), None)
            if not stream or not stream.get("width") or not stream.get("height"):
                self._unavailable(scene_index, "받은 파일에 영상 스트림이 없습니다", query)
            os.replace(partial, target)
            return size, stream
        finally:
            partial.unlink(missing_ok=True)

    def clip(self, scene_index, background, out_path):
        """`background` is ignored: stock footage needs no generated first frame."""
        self._authorized(scene_index)
        out_path = self._out(out_path)
        queries = self.config["queries"]
        query = queries[scene_index]
        occurrence = queries[:scene_index].count(query)
        key = digest({"query": query, "pick": occurrence, "contract": CONTRACT, "orientation": "portrait", "min_width": MIN_WIDTH})[:40]
        self.assets.mkdir(parents=True, exist_ok=True)
        with _lock(self.assets / ("stock-job-" + digest(self.job_id)[:32] + ".lock")):
            video_path, receipt_path = self.assets / (key + ".mp4"), self.assets / (key + ".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
            if receipt and receipt.get("status") == "complete" and video_path.is_file() and _hash(video_path) == receipt.get("sha256"):
                self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(video_path, out_path)
                return receipt["clip_metadata"]
            if not os.environ.get("PEXELS_API_KEY"):
                self._unavailable(scene_index, "PEXELS_API_KEY가 설정되지 않아 실사 영상을 받지 않았습니다. 이 장면은 정지 화면으로 만듭니다", query)
            if self._downloads() >= MAX_DOWNLOADS_PER_JOB:
                self._unavailable(scene_index, f"실사 영상 다운로드는 업무당 최대 {MAX_DOWNLOADS_PER_JOB}개입니다", query)
            videos = self._search(scene_index, query)
            candidates = [(video, choose_file(video)) for video in videos if isinstance(video, dict)]
            candidates = [(video, chosen) for video, chosen in candidates if chosen]
            if not candidates:
                self._unavailable(scene_index, f"'{query}' 검색에서 세로 720px 이상 MP4 영상을 찾지 못했습니다", query)
            video, chosen = candidates[occurrence % len(candidates)]
            size, stream = self._download(scene_index, query, chosen["link"], video_path)
            user = video.get("user") if isinstance(video.get("user"), dict) else {}
            attribution = {"source": "Pexels", "name": str(user.get("name") or "Pexels")[:120], "user_url": str(user.get("url") or "")[:300],
                           "page_url": str(video.get("url") or "")[:300], "pexels_video_id": video.get("id"), "license_url": LICENSE_URL}
            metadata = {"provider": "pexels", "model": "stock-footage", "disclosure": "Pexels 무료 실사 스톡 영상", "query": query,
                        "width": chosen["width"], "height": chosen["height"], "sha256": _hash(video_path), "attribution": attribution}
            _json(receipt_path, {"status": "complete", "query": query, "pick": occurrence, "pexels_video_id": video.get("id"),
                                 "page_url": attribution["page_url"], "file_url": chosen["link"], "file_id": chosen.get("id"),
                                 "user_name": attribution["name"], "user_url": attribution["user_url"], "license_url": LICENSE_URL,
                                 "sha256": metadata["sha256"], "bytes": size, "probe": {"width": stream.get("width"), "height": stream.get("height")},
                                 "downloaded_at": now(), "clip_metadata": metadata})
            self.store.event("stock_footage_downloaded", {"scene": scene_index + 1, "query": query, "pexels_video_id": video.get("id"),
                                                          "bytes": size, "paid_call_made": False}, self.job_id)
            self._authorized(scene_index); out_path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(video_path, out_path)
            return metadata


def make_pexels_clip_renderer(store, *, job_id, session=None, probe=None):
    provider = StockFootage(store, job_id=job_id, session=session, probe=probe)

    def render(scene_index, background, out_path):
        return provider.clip(scene_index, background, out_path)
    render.cache_key = provider.cache_key
    render.asset_cache_key = provider.asset_cache_key
    render.stock_provider = provider
    render.generated_scenes = list(range(len(provider.config["queries"])))
    render.needs_background = False
    render.fallback_to_still = True
    render.fallback_errors = (StockFootageUnavailable,)
    return render
