"""OpenAI speech tests use synthetic PCM; no network request is made here."""
import json
import math
import struct
import wave

import pytest
import requests

from office.store import Store, WorkflowError

NARRATIONS = ["근거를 확인합니다.", "원고를 승인합니다.", "선택한 결과를 제작합니다."]


def approved_fixture(tmp_path, approve=True):
    store = Store(tmp_path / "state")
    job = store.create_job({"id": "openai-speech-test", "title": "OpenAI 음성 시험"})
    packet = {"title": "합성 음성 시험", "body": "실제 뉴스가 아닌 기능 시험입니다.",
              "quality": {"status": "passed", "critical": []},
              "video": {"scenes": [{"narration": text, "caption": text} for text in NARRATIONS]}}
    job = store.save_source(job["id"], packet)
    if approve:
        store.review_source(job["id"], job["source_hash"], "approved", "기능 시험 승인", {"video": True})
    return store, job["id"]


def pcm_bytes(seconds=2.0, rate=24000):
    return b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 330 * i / rate))) for i in range(int(seconds * rate)))


class Response:
    def __init__(self, status=200, content=None):
        self.status_code = status
        self.content = pcm_bytes() if content is None else content
        self.headers = {"Content-Type": "audio/pcm"}


class Recorder:
    def __init__(self, response=None):
        self.calls, self.response = [], response or Response()

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def renderer_for(store, job_id, transport, allow_paid=True):
    from office.openai_speech import make_openai_voice_renderer
    return make_openai_voice_renderer(store, job_id=job_id, allow_paid=allow_paid, transport=transport)


def cost_rows(store):
    with store.connection() as db:
        return [dict(row) for row in db.execute("SELECT state,reserved_krw,actual_krw,data FROM costs")]


def test_paid_voice_requires_explicit_opt_in_and_key(tmp_path, monkeypatch):
    store, job_id = approved_fixture(tmp_path)
    transport = Recorder()
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    with pytest.raises(WorkflowError, match="명시|유료"):
        renderer_for(store, job_id, transport, allow_paid=False)(NARRATIONS[0], store.root / "out.wav")
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(WorkflowError, match="OPENAI_API_KEY"):
        renderer_for(store, job_id, transport)(NARRATIONS[0], store.root / "out.wav")
    assert transport.calls == [] and cost_rows(store) == []
    assert not (store.root / "out.wav").exists()


def test_requires_source_approval_before_construction(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path, approve=False)
    with pytest.raises(WorkflowError, match="승인"):
        renderer_for(store, job_id, Recorder())


def test_success_writes_24khz_mono_wav_settles_estimate_and_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    transport = Recorder()
    render = renderer_for(store, job_id, transport)
    target = store.root / "artifacts" / "voice.partial.wav"
    metadata = render(NARRATIONS[0], target)
    url, kwargs = transport.calls[0]
    assert url == "https://api.openai.com/v1/audio/speech"
    assert kwargs["headers"]["Authorization"] == "Bearer test-placeholder"
    body = kwargs["json"]
    assert body["model"] == "gpt-4o-mini-tts" and body["input"] == NARRATIONS[0]
    assert body["response_format"] == "pcm" and body["voice"] == "marin"
    assert "한국어" in body["instructions"]
    with wave.open(str(target), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (24000, 1, 2)
        assert audio.getnframes() == 48000
    assert metadata["provider"] == "openai" and metadata["model"] == "gpt-4o-mini-tts" and metadata["voice"] == "marin"
    assert "AI" in metadata["disclosure"] or "합성" in metadata["disclosure"]
    rows = cost_rows(store)
    assert len(rows) == 1 and rows[0]["state"] == "settled"
    usage = json.loads(rows[0]["data"])["usage"]
    assert usage["estimated"] is True and usage["cost_status"] == "provider_usage_estimate_pending_invoice"
    assert usage["audio_seconds"] == 2.0 and usage["audio_output_tokens_estimate"] == 100
    # 2s × 50 tok/s × $12/1M + UTF-8 input bytes × $0.60/1M, at 2,000 KRW/USD → rounds up to 3 KRW.
    assert rows[0]["actual_krw"] == math.ceil(usage["estimated_krw"]) == 3
    budget = store.budget()
    assert budget["reserved_krw"] == 0 and budget["spent_krw"] == 3
    again = store.root / "artifacts" / "again.wav"
    assert render(NARRATIONS[0], again) == metadata
    assert again.read_bytes() == target.read_bytes() and len(transport.calls) == 1
    assert store.budget() == budget
    receipts = list((store.root / "openai-speech-assets").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["status"] == "complete" and receipt["cost_estimated"] is True
    assert "test-placeholder" not in receipts[0].read_text(encoding="utf-8")


def test_client_error_is_settled_zero_and_server_error_stays_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    with pytest.raises(WorkflowError, match="HTTP 400"):
        renderer_for(store, job_id, Recorder(Response(400, b'{"error":{}}')))(NARRATIONS[0], store.root / "out.wav")
    rows = cost_rows(store)
    assert [(r["state"], r["actual_krw"]) for r in rows] == [("settled", 0)]
    with pytest.raises(WorkflowError, match="HTTP 503"):
        renderer_for(store, job_id, Recorder(Response(503, b"busy")))(NARRATIONS[1], store.root / "out.wav")
    states = sorted(r["state"] for r in cost_rows(store))
    assert states == ["settled", "unknown"]
    assert store.budget()["reserved_krw"] > 0


def test_network_uncertainty_keeps_reservation_and_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    calls = []

    def lost(*a, **k):
        calls.append(1)
        raise requests.Timeout("not printed")
    render = renderer_for(store, job_id, lost)
    for _ in range(2):
        with pytest.raises(WorkflowError, match="불명|예약"):
            render(NARRATIONS[0], store.root / "out.wav")
    assert len(calls) == 1
    assert [r["state"] for r in cost_rows(store)] == ["unknown"]


def test_unreadable_audio_is_settled_at_bound_and_needs_review(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    render = renderer_for(store, job_id, Recorder(Response(200, b"\x01")))
    with pytest.raises(WorkflowError, match="검토"):
        render(NARRATIONS[0], store.root / "out.wav")
    rows = cost_rows(store)
    assert len(rows) == 1 and rows[0]["state"] == "settled" and rows[0]["actual_krw"] == rows[0]["reserved_krw"]
    assert store.budget()["reserved_krw"] == 0
    with pytest.raises(WorkflowError, match="검토|불명"):
        render(NARRATIONS[0], store.root / "out.wav")
    assert len(cost_rows(store)) == 1


def test_unapproved_text_changed_source_and_bad_path_are_rejected_before_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    transport = Recorder()
    render = renderer_for(store, job_id, transport)
    with pytest.raises(WorkflowError, match="대본"):
        render("승인하지 않은 새 문장", store.root / "out.wav")
    with pytest.raises(WorkflowError, match="WAV|경로"):
        render(NARRATIONS[0], store.db_path)
    packet = store.job(job_id)["source_packet"]; packet["body"] += " 변경"
    store.save_source(job_id, packet)
    with pytest.raises(WorkflowError, match="승인|버전"):
        render(NARRATIONS[0], store.root / "out.wav")
    assert transport.calls == [] and cost_rows(store) == []


def test_job_cap_blocks_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    store.reserve_cost("speech_openai_tts", 990, {"job_id": job_id, "request_kind": "openai_tts", "cache_key": "prior"})
    transport = Recorder()
    with pytest.raises(WorkflowError, match="1,000"):
        renderer_for(store, job_id, transport)(NARRATIONS[0], store.root / "out.wav")
    assert transport.calls == []


def test_expired_price_and_closed_work_window_block_before_network(tmp_path, monkeypatch):
    import office.openai_speech as module
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    transport = Recorder()
    store.set_setting("work_window", {"authorized_end": "2000-01-01T00:00:00+00:00"})
    with pytest.raises(WorkflowError, match="작업 시간"):
        renderer_for(store, job_id, transport)(NARRATIONS[0], store.root / "out.wav")
    store.set_setting("work_window", {})
    monkeypatch.setattr(module, "PRICE_VALID_UNTIL", "2000-01-01T00:00:00+00:00")
    with pytest.raises(WorkflowError, match="단가"):
        renderer_for(store, job_id, transport)(NARRATIONS[0], store.root / "out.wav")
    assert transport.calls == [] and cost_rows(store) == []


def test_profile_selection_wires_openai_renderer_and_reports_configuration(tmp_path, monkeypatch):
    from office.voice_selection import profile_summary, renderer_for_job, select_profile
    from office.media import production_contract
    store, job_id = approved_fixture(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    summary = select_profile(store, "openai-tts", actor="test-operator")
    assert summary["paid"] is True and summary["configured"] is False and summary["job_cap_krw"] == 1000
    assert "OPENAI_API_KEY" in summary["key_source"] and summary["automatic_fallback"] is False
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    assert profile_summary(store)["configured"] is True
    job = store.job(job_id)
    renderer = renderer_for_job(store, job)
    assert renderer.speech_provider.config["model"] == "gpt-4o-mini-tts"
    assert production_contract(renderer, job["selections"])["hash"] != production_contract(None, job["selections"])["hash"]
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0
