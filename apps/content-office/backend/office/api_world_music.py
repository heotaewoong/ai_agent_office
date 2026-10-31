"""Authenticated, fixed licensed soundtrack; no credentials or workflow writes."""
from hashlib import sha256
from fastapi import HTTPException
from fastapi.responses import FileResponse

EXPECTED_SHA256 = "fb921a09cc6181228b14945c7a6b90b50a83f4f38a37644a383bf7c70ea83729"
CREDIT = "'Titan' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au"

def register(app, store):
    def verified():
        root = store.root.resolve()
        path = (root / "world-media" / "titan.mp3").resolve()
        try:
            if not path.is_relative_to(root) or not path.is_file():
                return None
            if not 0 < path.stat().st_size <= 20 * 1024 * 1024:
                return None
            if sha256(path.read_bytes()).hexdigest() != EXPECTED_SHA256:
                return None
        except OSError:
            return None
        return path

    @app.get("/api/world/music/status")
    def music_status():
        return {"available": verified() is not None, "title": "Titan",
                "creator": "Scott Buckley", "license": "CC BY 4.0", "credit": CREDIT,
                "source": "https://www.scottbuckley.com.au/library/titan/"}

    @app.get("/api/world/music/audio")
    def music_audio():
        path = verified()
        if path is None:
            raise HTTPException(404, "배경음악이 아직 준비되지 않았습니다")
        return FileResponse(path, media_type="audio/mpeg", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline"})
