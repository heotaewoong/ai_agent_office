"""Caption timings from matched source audio; never guesses missing dialogue."""
import re


def phrase_times(alignment, phrase, voice_offset):
    text = "".join(alignment["characters"])
    index = text.find(phrase)
    if index < 0 or not re.search(r"\w", phrase):
        raise ValueError("phrase not found in recorded speech alignment")
    start = voice_offset + alignment["character_start_times_seconds"][index]
    end = voice_offset + alignment["character_end_times_seconds"][index + len(phrase) - 1]
    if not 0 <= start < end:
        raise ValueError("invalid phrase time")
    return start, end


def scene_offsets(rows):
    offsets = {}
    for row in rows:
        points = row["points"]
        times = [p["source_start_estimate"] for p in points]
        if len(points) < 2 or min(p["correlation"] for p in points) < .6 or max(times) - min(times) > .02:
            raise ValueError("unreliable audio match; inspect actual selected cut")
        offsets[row["scene"]] = sum(times) / len(times)
    return offsets


def finalize_cues(cues, duration):
    result = [dict(c) for c in cues]
    for c in result:
        if not 0 <= c["start"] < c["end"] <= duration:
            raise ValueError("caption outside selected cut")
        if not all(re.search(r"\w", c.get(k, "")) for k in ("en", "ko")):
            raise ValueError("empty or punctuation-only caption")
    for previous, current in zip(result, result[1:]):
        if current["start"] <= previous["start"]:
            raise ValueError("caption order changed")
        if previous["end"] > current["start"]:
            if previous["end"] - current["start"] > .2:
                raise ValueError("large overlap requires content review")
            boundary = (previous["end"] + current["start"]) / 2
            previous["end"] = current["start"] = boundary
    return result
