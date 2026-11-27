import io

from office.memory_watch import note, rss_mb


def test_memory_note_only_for_big_jumps_or_high_rss():
    out = io.StringIO()
    assert note("GET", "/api/dashboard", 200, 260, 0.1, out) is None
    assert "rss 200MB -> 420MB (+220MB)" in note("POST", "/api/jobs/x/video", 200, 420, 3.0, out)
    assert "950MB" in note("GET", "/api/jobs/x", 940, 950, 0.2, out)
    assert note("GET", "/api/health", None, 300, 0.0, out) is None
    assert out.getvalue().count("MEMORY") == 2
    assert rss_mb() is None or rss_mb() > 0
