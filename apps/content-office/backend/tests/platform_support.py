"""Test-only helpers for environment limits that are not product defects."""
import os
import shutil

import pytest

requires_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg/ffprobe are not installed; video rendering is not exercised")


def symlink_or_skip(link, target, *, target_is_directory=False):
    """Create a symlink, or skip when Windows denies the privilege (Developer Mode off)."""
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Symlink creation needs Windows Developer Mode or administrator rights")
        raise
