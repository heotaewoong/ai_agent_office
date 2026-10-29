import io
import json
import os
import stat
import sys

import pytest
from PIL import Image

from office.store import Store, WorkflowError


def png_bytes(size=(64, 96)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 30, 60)).save(buffer, "PNG")
    return buffer.getvalue()


def approved_job(store, selections=None):
    job = store.create_job({"id": "codex-image", "title": "Codex 배경 시험"})
    packet = {"title": "합성 자료", "body": "Codex 배경 시험입니다.", "quality": {"status": "passed", "critical": []},
              "video": {"scenes": [{"narration": text, "caption": text} for text in ["근거를 확인합니다.", "원고를 승인합니다."]]}}
    job = store.save_source(job["id"], packet)
    store.review_source(job["id"], job["source_hash"], "approved", "fixture-operator", selections or {"video": True})
    return store.job(job["id"])


class FakeRunner:
    def __init__(self, raw=None, error=None):
        self.raw, self.error, self.prompts = raw or png_bytes(), error, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.raw, "01a188ad-a2d8-70e1-84cd-f26012a81c1d"


def test_background_uses_codex_once_then_reuses_receipt_without_budget(tmp_path, monkeypatch):
    from office.codex_image_provider import make_codex_background_renderer, used_today
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("Codex profile must never call the paid Images API"))
    store = Store(tmp_path)
    job = approved_job(store)
    runner = FakeRunner()
    render = make_codex_background_renderer(store, job_id=job["id"], runner=runner)
    meta = render(0, store.root / "out" / "background-01.png")
    assert meta["provider"] == "codex-subscription" and meta["size"] == "64x96" and meta["requested_size"] == "1024x1536"
    assert "Codex" in meta["disclosure"] and (store.root / "out" / "background-01.png").read_bytes() == runner.raw
    assert "1024px" in runner.prompts[0] and "1536px" in runner.prompts[0] and "근거를 확인합니다." in runner.prompts[0]
    again = render(0, store.root / "out" / "copy.png")
    assert again == meta and len(runner.prompts) == 1
    assert used_today(store) == 1
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0


def test_daily_cap_blocks_before_running_codex(tmp_path):
    from office.codex_image_provider import DAILY_CAP, make_codex_background_renderer, today
    store = Store(tmp_path)
    job = approved_job(store)
    store.set_setting("codex_image_usage", {"date": today(), "count": DAILY_CAP})
    runner = FakeRunner()
    render = make_codex_background_renderer(store, job_id=job["id"], runner=runner)
    with pytest.raises(WorkflowError, match="하루"):
        render(0, store.root / "out" / "background-01.png")
    assert runner.prompts == []


def test_failure_is_recorded_counted_and_not_retried_or_replaced(tmp_path):
    from office.codex_image_provider import make_codex_background_renderer, used_today
    store = Store(tmp_path)
    job = approved_job(store)
    runner = FakeRunner(error=WorkflowError("Codex 실행이 실패했습니다"))
    render = make_codex_background_renderer(store, job_id=job["id"], runner=runner)
    with pytest.raises(WorkflowError, match="Codex"):
        render(1, store.root / "out" / "background-02.png")
    receipts = [json.loads(p.read_text(encoding="utf-8")) for p in (store.root / "image-assets").glob("*.json")]
    assert [r["status"] for r in receipts] == ["failed"] and len(runner.prompts) == 1 and used_today(store) == 1
    assert not (store.root / "out" / "background-02.png").exists()


def test_non_png_output_is_rejected(tmp_path):
    from office.codex_image_provider import make_codex_background_renderer
    store = Store(tmp_path)
    job = approved_job(store)
    render = make_codex_background_renderer(store, job_id=job["id"], runner=FakeRunner(raw=b"not an image"))
    with pytest.raises(WorkflowError, match="PNG"):
        render(0, store.root / "out" / "background-01.png")


def test_unapproved_or_text_only_jobs_never_reach_codex(tmp_path):
    from office.codex_image_provider import make_codex_background_renderer
    store = Store(tmp_path)
    job = approved_job(store, {"blog": True})
    runner = FakeRunner()
    render = make_codex_background_renderer(store, job_id=job["id"], runner=runner)
    with pytest.raises(WorkflowError, match="영상 또는 카드"):
        render(0, store.root / "out" / "background-01.png")
    assert runner.prompts == []


def test_card_renderer_follows_codex_profile_unless_images_are_switched_off(tmp_path, monkeypatch):
    from office.cards import _card_renderer
    from office.codex_image_provider import CodexImageProvider
    from office.image_selection import select_profile
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store = Store(tmp_path)
    job = approved_job(store, {"cards": True})
    select_profile(store, "codex-subscription", actor="test-operator")
    notes = []
    assert isinstance(_card_renderer(store, job["id"], None, None, notes).image_provider, CodexImageProvider)
    assert _card_renderer(store, job["id"], False, None, notes) is None and notes == []


def fake_codex(tmp_path, body):
    script = tmp_path / "fake-codex"
    script.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.mark.skipif(os.name == "nt", reason="fake CLI uses a POSIX shebang")
def test_runner_reads_image_from_codex_home_and_hides_api_keys(tmp_path, monkeypatch):
    from office.codex_image_provider import run_codex
    home = tmp_path / "codex-home"
    (home / "generated_images").mkdir(parents=True)
    raw = png_bytes()
    (tmp_path / "image.png").write_bytes(raw)
    script = fake_codex(tmp_path, f"""
import json, os, pathlib, shutil, sys
thread = "01a188ad-a2d8-70e1-84cd-f26012a81c1d"
folder = pathlib.Path(os.environ["CODEX_HOME"]) / "generated_images" / thread
folder.mkdir(parents=True)
shutil.copyfile({str(tmp_path / "image.png")!r}, folder / "exec-1.png")
pathlib.Path({str(tmp_path / "seen.json")!r}).write_text(json.dumps({{"argv": sys.argv[1:], "keys": [k for k in ("OPENAI_API_KEY", "CODEX_API_KEY") if k in os.environ]}}))
print(json.dumps({{"type": "thread.started", "thread_id": thread}}))
print(json.dumps({{"type": "turn.completed"}}))
""")
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", str(script))
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("CODEX_API_KEY", "sk-should-not-leak")
    got, thread = run_codex("배경 한 장")
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert got == raw and thread == "01a188ad-a2d8-70e1-84cd-f26012a81c1d"
    assert seen["keys"] == [] and seen["argv"][:5] == ["exec", "--skip-git-repo-check", "--sandbox", "read-only", "--json"]
    assert not (home / "generated_images" / thread).exists()


@pytest.mark.skipif(os.name == "nt", reason="fake CLI uses a POSIX shebang")
def test_runner_rejects_failed_runs_and_missing_images(tmp_path, monkeypatch):
    from office.codex_image_provider import run_codex
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", str(fake_codex(tmp_path, "import sys\nprint('not logged in', file=sys.stderr)\nsys.exit(1)\n")))
    with pytest.raises(WorkflowError, match="로그인"):
        run_codex("배경 한 장")
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", str(fake_codex(tmp_path, "import json\nprint(json.dumps({'type': 'thread.started', 'thread_id': '01a188ad-a2d8-70e1-84cd-f26012a81c1d'}))\n")))
    with pytest.raises(WorkflowError, match="0장"):
        run_codex("배경 한 장")
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", "definitely-not-installed-codex")
    with pytest.raises(WorkflowError, match="설치"):
        run_codex("배경 한 장")


def test_status_needs_cli_and_login_file_without_reading_it(tmp_path, monkeypatch):
    from office.codex_image_provider import codex_status
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", sys.executable)
    assert codex_status()["configured"] is False
    (home / "auth.json").write_text("{}")
    assert codex_status()["configured"] is True
    monkeypatch.setenv("CONTENT_OFFICE_CODEX_BIN", "definitely-not-installed-codex")
    assert codex_status()["configured"] is False
