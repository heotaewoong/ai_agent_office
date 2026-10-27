"""Budget/caching tests use synthetic PCM; no network request is made here."""
import base64
import io
import json
import math
import struct
import wave
from pathlib import Path

import pytest
import requests

from office.store import Store, WorkflowError


def approved_fixture(tmp_path):
    store = Store(tmp_path / "state")
    job = store.create_job({"id": "speech-test", "title": "승인된 합성 음성 시험"})
    packet = {"title": "합성 음성 시험", "body": "실제 뉴스가 아닌 합성 기능 시험입니다.", "synthetic_fixture": True,
              "quality": {"status": "passed", "critical": []}, "video": {"scenes": [{"narration": "한국어 음성을 확인합니다."}]}}
    job = store.save_source(job["id"], packet)
    store.review_source(job["id"], job["source_hash"], "approved", "합성 기능 시험 승인", {"video": True})
    return store, job["id"]


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(24000)
        audio.writeframes(b"".join(struct.pack("<h", int(5000*math.sin(2*math.pi*330*i/24000))) for i in range(12000)))
    return out.getvalue()


class AudioResponse:
    status_code = 200
    def __init__(self, usage=True): self.usage = usage
    def json(self):
        data = {"id": "interaction_synthetic_tts", "status": "completed", "steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(wav_bytes()).decode()}]}]}
        if self.usage:
            data["usage"] = {"total_input_tokens": 100, "total_output_tokens": 200, "total_thought_tokens": 0, "output_tokens_by_modality": [{"modality": "audio", "tokens": 200}]}
        return data


def test_paid_voice_disabled_has_no_cost_or_asset(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=False)
    with pytest.raises(WorkflowError, match="명시|유료"):
        renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0
    assert not (store.root/"out.wav").exists()


def test_success_persists_wav_usage_receipt_and_reuses_without_new_charge(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=lambda *a,**k: AudioResponse())
    target = store.root/"out.wav"
    metadata = renderer("한국어 음성을 확인합니다.", target)
    first_budget = store.budget()
    renderer("한국어 음성을 확인합니다.", store.root/"again.wav")
    assert target.read_bytes() == (store.root/"again.wav").read_bytes() == wav_bytes()
    assert metadata["provider"] == "gemini" and metadata["model"] == "gemini-3.8-flash-tts"
    assert first_budget == store.budget()
    assert first_budget["spent_krw"] == 4 and first_budget["reserved_krw"] == 0
    receipts = list((store.root/"speech-assets").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt["status"] == "complete" and receipt["response_id"] == "interaction_synthetic_tts"
    assert receipt["sha256"] and receipt["usage"]["total_output_tokens"] == 200
    assert "test-placeholder" not in receipts[0].read_text()


def test_missing_usage_preserves_received_audio_and_unknown_reservation(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=lambda *a,**k: AudioResponse(usage=False))
    for _ in range(2):
        with pytest.raises(WorkflowError, match="사용량|불명|예약"):
            renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert len(list((store.root/"speech-assets").glob("*.wav"))) == 1
    assert store.budget()["reserved_krw"] == 400
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 1


def test_network_uncertainty_is_not_retried(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    def lost(*a, **k): raise requests.Timeout("not printed")
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=lost)
    for _ in range(2):
        with pytest.raises(WorkflowError, match="불명|예약"):
            renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["reserved_krw"] == 400
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 1


def test_experiment_subcap_and_global_cap_both_block_before_network(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    store.reserve_cost("synthetic-prior", 700, {"experiment_id": "test-voice", "cache_key": "prior"})
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True)
    with pytest.raises(WorkflowError, match="1,000|1000|실험"):
        renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["reserved_krw"] == 700


def test_changed_source_and_unapproved_text_are_rejected_before_cost(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True)
    with pytest.raises(WorkflowError, match="원고|대본"):
        renderer("승인하지 않은 새 문장", store.root/"out.wav")
    packet = store.job(job_id)["source_packet"]; packet["body"] += " 변경"
    store.save_source(job_id, packet)
    with pytest.raises(WorkflowError, match="승인|버전"):
        renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["reserved_krw"] == 0


def test_paid_callback_cannot_overwrite_database_or_non_wav_files(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    before = store.db_path.read_bytes()
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=lambda *a,**k: AudioResponse())
    with pytest.raises(WorkflowError, match="WAV|wav|경로"):
        renderer("한국어 음성을 확인합니다.", store.db_path)
    assert store.db_path.read_bytes() == before
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0


def test_asr_uses_audio_without_expected_transcript_and_settles_real_usage(tmp_path, monkeypatch):
    from office.speech_provider import SpeechProvider
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    audio = store.root/"baseline.wav"; audio.write_bytes(wav_bytes())
    requests_seen = []
    class TranscriptResponse:
        status_code = 200
        def json(self):
            return {"id": "asr_synthetic", "status": "completed", "usage": {"total_input_tokens": 1000, "total_output_tokens": 40, "total_thought_tokens": 20}, "steps": [{"type":"model_output", "content":[{"type":"text", "text":"한국어 음성을 확인합니다."}]}]}
    def transport(*args, **kwargs):
        requests_seen.append(kwargs["json"])
        return TranscriptResponse()
    provider = SpeechProvider(store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=transport)
    result = provider.transcribe(audio)
    first_budget = store.budget()
    assert provider.transcribe(audio) == result
    assert result["text"] == "한국어 음성을 확인합니다."
    assert result["usage"]["total_thought_tokens"] == 20
    assert first_budget == store.budget() and first_budget["spent_krw"] == 1
    assert len(requests_seen) == 1
    assert requests_seen[0]["input"][1]["type"] == "audio"
    assert "한국어 음성을 확인합니다." not in requests_seen[0]["input"][0]["text"]


def test_global_budget_cap_blocks_even_when_experiment_has_room(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    store.reserve_cost("prior-other-work", 9800, {"cache_key":"other-work"})
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid=True)
    with pytest.raises(WorkflowError, match="예산"):
        renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["reserved_krw"] == 9800


def test_fixture_authorization_can_be_separate_while_charges_use_shared_global_ledger(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    fixture_store, job_id = approved_fixture(tmp_path)
    ledger = Store(tmp_path/"shared-global-ledger")
    renderer = make_gemini_voice_renderer(ledger, source_store=fixture_store, job_id=job_id, experiment_id="test-voice", allow_paid=True, transport=lambda *a,**k: AudioResponse())
    renderer("한국어 음성을 확인합니다.", ledger.root/"out.wav")
    assert ledger.budget()["spent_krw"] == 4
    assert fixture_store.budget()["spent_krw"] == fixture_store.budget()["reserved_krw"] == 0
    assert ledger.jobs() == []


def test_string_false_cannot_accidentally_enable_paid_speech(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, experiment_id="test-voice", allow_paid="false", transport=lambda *a,**k: AudioResponse())
    with pytest.raises(WorkflowError, match="명시|유료"):
        renderer("한국어 음성을 확인합니다.", store.root/"out.wav")
    assert store.budget()["spent_krw"] == store.budget()["reserved_krw"] == 0


def production_fixture(tmp_path, count=3):
    store, job_id = approved_fixture(tmp_path)
    packet = store.job(job_id)["source_packet"]
    packet.pop("synthetic_fixture")
    packet["video"]["scenes"] = [{"narration": f"승인한 장면 {index+1}의 대본입니다."} for index in range(count)]
    job = store.save_source(job_id, packet)
    store.review_source(job_id, job["source_hash"], "approved", "시험용 명시 승인", {"video": True})
    return store, job_id


def test_production_allows_seven_unique_approved_scenes_and_reuses_each(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = production_fixture(tmp_path, count=7)
    renderer = make_gemini_voice_renderer(store, job_id=job_id, synthetic_only=False, allow_paid=True, transport=lambda *a,**k: AudioResponse())
    for index, scene in enumerate(store.job(job_id)["source_packet"]["video"]["scenes"]):
        renderer(scene["narration"], store.root/f"scene-{index}.wav")
    before = store.budget()
    renderer("승인한 장면 1의 대본입니다.", store.root/"again.wav")
    assert store.budget() == before and before["spent_krw"] == 28
    with store.connection() as db: assert db.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 7


def test_production_scope_cannot_reset_subcap_with_another_experiment_name(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = production_fixture(tmp_path)
    one = make_gemini_voice_renderer(store,job_id=job_id,experiment_id="first",synthetic_only=False,allow_paid=True)
    two = make_gemini_voice_renderer(store,job_id=job_id,experiment_id="reset",synthetic_only=False,allow_paid=True)
    assert one.speech_provider.experiment_id == two.speech_provider.experiment_id
    store.reserve_cost("prior-production-voice",700,{"experiment_id":one.speech_provider.experiment_id,"cache_key":"prior"})
    with pytest.raises(WorkflowError,match="1,000|실험|한도"):
        two("승인한 장면 1의 대본입니다.",store.root/"out.wav")
    assert store.budget()["reserved_krw"] == 700


def test_video_deselection_blocks_paid_voice_even_with_current_source_approval(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    job = store.job(job_id)
    store.review_source(job_id,job["source_hash"],"approved","명시 검토",{"blog":True,"video":False})
    renderer=make_gemini_voice_renderer(store,job_id=job_id,experiment_id="test-voice",allow_paid=True,transport=lambda *a,**k: AudioResponse())
    with pytest.raises(WorkflowError,match="영상|선택"):
        renderer("한국어 음성을 확인합니다.",store.root/"out.wav")
    assert store.budget()["spent_krw"] == 0


def test_known_usage_overrun_is_settled_and_flagged_not_hidden_as_unknown(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = approved_fixture(tmp_path)
    class Overrun(AudioResponse):
        def json(self):
            data=super().json();data["usage"]["total_output_tokens"]=30000
            data["usage"]["output_tokens_by_modality"][0]["tokens"]=30000
            return data
    renderer=make_gemini_voice_renderer(store,job_id=job_id,experiment_id="test-voice",allow_paid=True,transport=lambda *a,**k:Overrun())
    with pytest.raises(WorkflowError,match="초과|상한|계약"):
        renderer("한국어 음성을 확인합니다.",store.root/"out.wav")
    assert store.budget()["spent_krw"] == 541 and store.budget()["reserved_krw"] == 0
    with store.connection() as db:
        row=db.execute("SELECT state,data FROM costs").fetchone()
    assert row["state"] == "settled" and json.loads(row["data"])["reservation_overrun"] == 141
    assert any(event["kind"]=="cost_exceeded_reservation" for event in store.events())


def test_pure_profile_and_factory_prices_limits_style_are_snapshot_immutable(tmp_path, monkeypatch):
    from office.speech_provider import voice_profile_config, make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    profile=voice_profile_config()
    assert profile["request_limits"] == {"tts":1,"asr":2}
    store, job_id = approved_fixture(tmp_path)
    renderer=make_gemini_voice_renderer(store,job_id=job_id,experiment_id="test-voice",allow_paid=True)
    before=renderer.cache_key
    copy=renderer.speech_provider.config
    copy["style"]="다른 발음 지시";copy["pricing"]["tts_audio_usd_million"]=0
    copy["request_limits"]["tts"]=999
    assert renderer.speech_provider.config["style"] != copy["style"]
    assert renderer.speech_provider.config["pricing"]["tts_audio_usd_million"] == 9.0
    assert renderer.speech_provider.config["request_limits"]["tts"] == 1
    assert renderer.cache_key == before
    changed=make_gemini_voice_renderer(store,job_id=job_id,experiment_id="test-voice",allow_paid=True,style="약어를 또렷하게 읽으세요")
    assert changed.cache_key != before


def test_production_stops_other_scene_calls_after_known_provider_overrun(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = production_fixture(tmp_path)
    class Overrun(AudioResponse):
        def json(self):
            data=super().json();data["usage"]["total_output_tokens"]=30000
            return data
    renderer=make_gemini_voice_renderer(store,job_id=job_id,synthetic_only=False,allow_paid=True,transport=lambda *a,**k:Overrun())
    with pytest.raises(WorkflowError,match="초과|상한"):
        renderer("승인한 장면 1의 대본입니다.",store.root/"first.wav")
    with pytest.raises(WorkflowError,match="초과|대사|차단"):
        renderer("승인한 장면 2의 대본입니다.",store.root/"second.wav")
    assert store.budget()["spent_krw"] == 541
    with store.connection() as db: assert db.execute("SELECT COUNT(*) FROM costs").fetchone()[0] == 1


def test_source_version_change_preserves_asset_identity_but_changes_full_contract(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    store, job_id = production_fixture(tmp_path)
    first=make_gemini_voice_renderer(store,job_id=job_id,synthetic_only=False,allow_paid=True)
    packet=store.job(job_id)["source_packet"];packet["body"] += " 원고 근거의 설명만 보완했습니다."
    job=store.save_source(job_id,packet)
    store.review_source(job_id,job["source_hash"],"approved","다시 검토",{"video":True})
    revised=make_gemini_voice_renderer(store,job_id=job_id,synthetic_only=False,allow_paid=True)
    assert first.cache_key != revised.cache_key
    assert first.asset_cache_key == revised.asset_cache_key
    other_style=make_gemini_voice_renderer(store,job_id=job_id,synthetic_only=False,allow_paid=True,style="약어를 또렷하게 읽으세요")
    assert other_style.asset_cache_key != revised.asset_cache_key


def test_production_job_subcap_is_not_reset_by_source_revision(tmp_path, monkeypatch):
    from office.speech_provider import make_gemini_voice_renderer
    monkeypatch.setenv('GEMINI_API_KEY', 'test-placeholder')
    store, job_id = production_fixture(tmp_path)
    first = make_gemini_voice_renderer(store, job_id=job_id, synthetic_only=False, allow_paid=True)
    store.reserve_cost('prior-production-voice', 700, {'experiment_id': first.speech_provider.experiment_id, 'job_id': job_id, 'request_kind': 'tts', 'cache_key': 'prior-source-voice'})
    packet = store.job(job_id)['source_packet']; packet['body'] += ' 수정했습니다.'
    current = store.save_source(job_id, packet)
    store.review_source(job_id, current['source_hash'], 'approved', 'fixture-operator', {'video': True})
    revised = make_gemini_voice_renderer(store, job_id=job_id, synthetic_only=False, allow_paid=True, transport=lambda *a, **k: AudioResponse())
    with pytest.raises(WorkflowError, match='1,000|1000|한도'):
        revised('승인한 장면 1의 대본입니다.', store.root / 'new-version.wav')
    assert store.budget()['reserved_krw'] == 700
