"""One synthetic opt-in voice comparison; no real-news packet/media writes.

Run without --execute for the specific proposal and maximum reservation only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import wave

from .media import local_voice, audio_duration
from .speech_provider import SpeechProvider
from .store import Store, WorkflowError, digest

TEXT = "Gemini API와 AI 에이전트를 확인합니다. 검토 시간은 30% 줄었고, 검증 기간은 3개월입니다."
EXPERIMENT_ID = "korean-voice-synthetic-20261026-v1"


def proposal():
    return {"experiment_id": EXPERIMENT_ID, "synthetic_only": True, "text": TEXT,
            "paid_requests": {"tts": 1, "asr": 2}, "request_reservation_maxima_krw": {"tts": 400, "asr_each": 100},
            "maximum_open_reservations_krw": 600, "experiment_cap_krw": 1000,
            "tts_model": "gemini-3.8-flash-tts", "asr_model": "gemini-3.5-flash-lite",
            "local_baseline": "Microsoft Heami Desktop; rate 0", "automatic_fallback": False}


def _write(path, data):
    partial = path.with_name(path.name+".partial")
    partial.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(partial,path)


def _terms(text):
    normalized = re.sub(r"\s+", "", text.lower())
    targets = {"Gemini": ["gemini","제미나이","제미니"], "API": ["api","에이피아이"],
               "AI 에이전트": ["ai에이전트","에이아이에이전트"], "30%": ["30%","삼십퍼센트","30퍼센트"],
               "3개월": ["3개월","삼개월","세개월"]}
    return [{"target":target,"asr_variants_found":[v for v in variants if v in normalized]} for target,variants in targets.items()]


def execute(ledger_root, fixture_root):
    ledger_root = Path(ledger_root).expanduser().resolve()
    if not (ledger_root/"office.sqlite3").is_file():
        raise WorkflowError("기존 전체 예산 장부를 지정해야 합니다. 새 장부로 유료 한도를 우회하지 않습니다")
    ledger, fixtures = Store(ledger_root), Store(fixture_root)
    original_news = {job["id"]:job.get("source_hash") for job in ledger.jobs()}
    budget_before = ledger.budget()
    job = fixtures.create_job({"id":EXPERIMENT_ID,"title":"합성 한국어 음성 비교 시험","url":"https://example.com/synthetic-voice-fixture"})
    packet = {"title":"합성 한국어 음성 비교 시험", "body":"실제 뉴스가 아닌 허용된 합성 음성 시험 자료입니다.\n\n"+TEXT,
              "synthetic_fixture":True,"quality":{"status":"passed","critical":[],"method":"authorized-synthetic-functional-fixture; model evaluation not run"},
              "video":{"title":"합성 음성 시험","description":"실제 뉴스가 아닙니다.","tags":[],"scenes":[{"narration":TEXT,"caption":"외래어·약어·숫자 읽기 시험","visual":"explanation"}]}}
    job = fixtures.save_source(job["id"],packet)
    if (job.get("source_approval") or {}).get("decision") != "approved":
        fixtures.review_source(job["id"],job["source_hash"],"approved","허용된 합성 음성 비교 기능 시험",{"video":True})
    provider = SpeechProvider(ledger,source_store=fixtures,job_id=job["id"],experiment_id=EXPERIMENT_ID,allow_paid=True)
    folder = ledger.root/"voice-experiments"/EXPERIMENT_ID
    folder.mkdir(parents=True,exist_ok=True)
    report = {**proposal(),"started_at":datetime.now(timezone.utc).isoformat(),"fixture_job_id":job["id"],"fixture_source_hash":job["source_hash"],
              "budget_before":budget_before,"subjective_listening":"not_performed","status":"started","stages":[]}
    path = folder/"report.json"
    _write(path,report)
    try:
        baseline = folder/"heami.wav"
        baseline_receipt = folder/"heami.json"
        if not baseline.is_file() or not baseline_receipt.is_file():
            previous_voice = os.environ.get("OFFICE_LOCAL_VOICE")
            os.environ["OFFICE_LOCAL_VOICE"] = "Microsoft Heami Desktop"
            partial = baseline.with_name("heami.partial.wav")
            try:
                meta = local_voice(TEXT,partial)
                duration = audio_duration(partial)
                os.replace(partial,baseline)
                _write(baseline_receipt,{"voice":meta,"duration":duration,"text_hash":digest(TEXT),"rate":0})
            finally:
                partial.unlink(missing_ok=True)
                if previous_voice is None: os.environ.pop("OFFICE_LOCAL_VOICE",None)
                else: os.environ["OFFICE_LOCAL_VOICE"] = previous_voice
        baseline_meta = json.loads(baseline_receipt.read_text(encoding="utf-8"))
        if baseline_meta["text_hash"] != digest(TEXT): raise WorkflowError("기준 음성의 대본이 달라졌습니다")
        report["stages"].append({"kind":"local_baseline","path":str(baseline),**baseline_meta});_write(path,report)
        # Verify the current REST/usage contract on the known model before paid TTS.
        heami_asr = provider.transcribe(baseline)
        report["stages"].append({"kind":"heami_asr",**heami_asr,"term_observations":_terms(heami_asr["text"])});_write(path,report)
        generated = folder/"gemini-kore.wav"
        metadata = provider.tts(TEXT,generated)
        duration = audio_duration(generated)
        report["stages"].append({"kind":"gemini_tts","path":str(generated),"voice":metadata,"duration":duration});_write(path,report)
        gemini_asr = provider.transcribe(generated)
        report["stages"].append({"kind":"gemini_asr",**gemini_asr,"term_observations":_terms(gemini_asr["text"])});_write(path,report)
        report["status"] = "completed_for_human_review"
    except WorkflowError as error:
        report.update(status="stopped_without_retry",error=str(error))
    finally:
        with ledger.connection() as db:
            calls=[]
            for row in db.execute("SELECT id,kind,state,reserved_krw,actual_krw,data FROM costs"):
                data=json.loads(row["data"])
                if data.get("experiment_id")==EXPERIMENT_ID:
                    calls.append({k:row[k] for k in ("id","kind","state","reserved_krw","actual_krw")})
        after = {job["id"]:job.get("source_hash") for job in ledger.jobs()}
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),cost_calls=calls,
                      experiment_spent_krw=sum(c["actual_krw"] or 0 for c in calls if c["state"]=="settled"),
                      experiment_open_reservations_krw=sum(c["reserved_krw"] for c in calls if c["state"] in ("reserved","unknown")),
                      budget_after=ledger.budget(),real_news_packets_unchanged=original_news==after,
                      comparison_limit="동일 ASR의 전사 관찰이며 자연스러움·발음 품질의 사람 청취 판정이 아닙니다. ASR은 표기를 정규화할 수 있습니다.")
        _write(path,report)
    return path,report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--ledger-root",default=str(Path.home()/".local/state/heobrain-content-office"))
    parser.add_argument("--fixture-root",default=str(Path.home()/".local/state/heobrain-content-office-media-verification-20261026"))
    args=parser.parse_args()
    if not args.execute: print(json.dumps(proposal(),ensure_ascii=False,indent=2))
    else:
        path,report=execute(args.ledger_root,args.fixture_root)
        print(json.dumps({"report":str(path),"status":report["status"],"error":report.get("error"),"spent_krw":report["experiment_spent_krw"],"open_reservations_krw":report["experiment_open_reservations_krw"],"real_news_packets_unchanged":report["real_news_packets_unchanged"]},ensure_ascii=False,indent=2))
