import hashlib
import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / 'cinematic_review.py'
spec = importlib.util.spec_from_file_location('cinematic_review', MODULE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_cues_reject_overlap_and_out_of_clip():
    review.validate_cues([{'start': .2, 'end': 1, 'en': 'A', 'ko': '가'}], 2)
    for cues in [
        [{'start': 0, 'end': 3, 'en': 'A', 'ko': '가'}],
        [{'start': 0, 'end': 1, 'en': 'A', 'ko': '가'},
         {'start': .9, 'end': 2, 'en': 'B', 'ko': '나'}],
        [{'start': 0, 'end': 1, 'en': '', 'ko': '가'}],
    ]:
        with pytest.raises(ValueError):
            review.validate_cues(cues, 2)


def test_paths_and_hashes_protect_original_and_skill(tmp_path):
    root = tmp_path / 'artifacts'
    root.mkdir()
    source = root / 'original.mp4'
    source.write_bytes(b'preserved original')
    skill = tmp_path / 'SKILL.md'
    skill.write_text('skill-v1', encoding='utf-8')
    plan = {
        'source_hash_snapshot': 'a' * 64,
        'source': {'path': str(source), 'sha256': review.sha256(source)},
        'skill': {'path': str(skill), 'sha256': review.sha256(skill)},
    }
    review.validate_snapshot(plan, 'a' * 64)
    with pytest.raises(ValueError, match='source version'):
        review.validate_snapshot(plan, 'b' * 64)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='input media'):
        review.validate_snapshot(plan, 'a' * 64)
    source.write_bytes(b'preserved original')
    skill.write_text('skill-v2', encoding='utf-8')
    with pytest.raises(ValueError, match='skill version'):
        review.validate_snapshot(plan, 'a' * 64)
    with pytest.raises(ValueError):
        review.inside(root, tmp_path / 'outside.mp4')


def test_unchanged_approvals_are_required():
    before = {'source_approval': None, 'release_approval': None, 'manifest': {'id': 1}}
    review.assert_approvals_unchanged(before, dict(before))
    with pytest.raises(ValueError):
        review.assert_approvals_unchanged(before, {**before, 'source_approval': {'id': 2}})


def test_review_files_cannot_be_inputs_or_unverified(tmp_path):
    source = tmp_path / 'baseline.mp4'
    source.write_bytes(b'input')
    with pytest.raises(ValueError):
        review.validate_outputs([source], source, tmp_path, {})
    f = tmp_path / 'pilot.mp4'
    f.write_bytes(b'output')
    with pytest.raises(ValueError):
        review.validate_outputs([f], source, tmp_path, {'whole_decode': False})
    review.validate_outputs([f], source, tmp_path, {'whole_decode': True})
