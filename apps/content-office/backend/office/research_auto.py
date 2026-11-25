"""자동 보충 조사: 기획을 열면 자료 창고를 먼저 보고, 판정(맞음, 애매, 틀림)에 따라 바깥 조사를 대신 눌러 준다.

- 맞음이면 밖으로 찾지 않는다. 애매와 틀림이면 무료 공개 출처와 Tavily 1회를 돈다. 내 경험(W4)과 범위 밖(W5)은 판정도 조사도 하지 않는다.
- Tavily 자동 호출은 기획마다 한 번, 하루(한국 시간) AUTO_TAVILY_DAILY_CAP회까지다. 넘으면 사람이 버튼으로만 부른다. 월 한도는 run_tavily가 지킨다.
- 같은 기획(제목, 요약, 고른 유형과 분야가 같을 때)은 저장한 결과를 돌려준다. 검색어는 기획 제목뿐이고 개인 DB 문장은 보내지 않는다.
- 찾은 것은 후보일 뿐이다. 창고에 넣고 근거로 고르는 일(기획 선택⓪)은 사람이 한다. 승인⓪①②③을 만들거나 대신하지 않는다.
"""
from __future__ import annotations

import hashlib
import json

from .external_research import run_research, run_tavily, tavily_usage
from .research_choices import auto_tavily_today, load_auto, save_auto

AUTO_TAVILY_DAILY_CAP = 30


def _key(title: str, summary: str, area, kind, experience_first: bool) -> str:
    text = json.dumps([title, summary, area, kind, bool(experience_first)], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def run_auto_research(root, idea_id: str, title: str, *, summary: str = "", area: str | None = None, kind: str | None = None,
                      experience_first: bool = False, translate=None, research=None, tavily=None) -> dict:
    research, tavily = research or run_research, tavily or run_tavily
    key = _key(title, summary, area, kind, experience_first)
    saved = load_auto(root, idea_id)
    if saved and saved["key"] == key and saved["result"]:
        return {**saved["result"], "cached": True}
    result = research(root, title, summary=summary, area=area, kind=kind, experience_first=experience_first, translate=translate, auto=True)
    verdict = (result.get("verdict") or {}).get("verdict")
    today, used = auto_tavily_today(root), False
    if verdict in ("ambiguous", "incorrect") and not (result.get("plan") or {}).get("blocked"):
        usage = tavily_usage(root)
        if saved and saved["tavily"]:
            result["notes"].append("이 기획은 Tavily 자동 검색을 이미 한 번 했어요. 더 찾으려면 버튼을 눌러 주세요.")
        elif today >= AUTO_TAVILY_DAILY_CAP:
            result["notes"].append(f"오늘 Tavily 자동 검색 {AUTO_TAVILY_DAILY_CAP}회를 다 썼어요. 버튼으로는 찾을 수 있어요.")
        elif usage["has_key"] and usage["remaining"] > 0:
            found = tavily(root, title)
            used = found["tavily"]["calls"] > usage["calls"]
            seen = {row["key"] for row in result["candidates"]}
            result["candidates"] = [*result["candidates"], *(row for row in found["candidates"] if row["key"] not in seen)]
            result["notes"] = [*result["notes"], *(note for note in found["notes"] if note not in result["notes"])]
            result["searched"] = bool(result.get("searched") or found["searched"])
            result["tavily"] = found["tavily"]
            today += int(used)
    if verdict == "incorrect" and not any(row.get("lane") != "example" for row in result["candidates"]):
        result["hold"] = True
        result["notes"].append("자료 창고와 바깥 모두에서 사실 근거를 찾지 못했어요. 근거 부족으로 보류하거나 검색어를 바꿔 다시 찾아 주세요.")
    result["auto"] = {"ran": bool(result.get("searched")), "tavily": used, "tavily_today": today, "tavily_daily_cap": AUTO_TAVILY_DAILY_CAP}
    save_auto(root, idea_id, key, result, tavily=used)
    return {**result, "cached": False}
