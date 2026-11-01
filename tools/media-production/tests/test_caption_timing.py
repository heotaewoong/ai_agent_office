import importlib.util
from pathlib import Path
import pytest

p = Path(__file__).parents[1] / "caption_timing.py"
spec = importlib.util.spec_from_file_location("caption_timing", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_phrase_uses_actual_character_times_after_nonspoken_tag():
    text = "[urgent] Go now."
    a = {"characters": list(text), "character_start_times_seconds": [i / 10 for i in range(len(text))],
         "character_end_times_seconds": [(i + 1) / 10 for i in range(len(text))]}
    assert m.phrase_times(a, "Go now.", 20) == pytest.approx((20.9, 21.6))
    with pytest.raises(ValueError): m.phrase_times(a, "Not spoken", 20)

def test_unreliable_scene_cannot_be_silently_reused():
    good = {"scene": 0, "points": [{"source_start_estimate": .3, "correlation": .8},
                                   {"source_start_estimate": .30025, "correlation": .7}]}
    bad = {"scene": 7, "points": [{"source_start_estimate": 80, "correlation": .29},
                                  {"source_start_estimate": 2, "correlation": .3}]}
    assert m.scene_offsets([good]) == {0: pytest.approx(.300125)}
    with pytest.raises(ValueError): m.scene_offsets([good, bad])

def test_caption_overlap_is_resolved_without_orphan_punctuation():
    cues = [{"start": 1, "end": 2.1, "en": "All units...", "ko": "전 군…"},
            {"start": 2, "end": 3, "en": "Charge!", "ko": "돌격하라!"}]
    out = m.finalize_cues(cues, 4)
    assert out[0]["end"] <= out[1]["start"]
    assert cues[0]["end"] == 2.1
    with pytest.raises(ValueError): m.finalize_cues([{"start":0,"end":1,"en":".","ko":"."}], 4)
    with pytest.raises(ValueError): m.finalize_cues([{"start":0,"end":8,"en":"A","ko":"가"}], 4)
