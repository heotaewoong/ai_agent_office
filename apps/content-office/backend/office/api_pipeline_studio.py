"""Read-only private drawing assets behind the existing signed operator session."""
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse


ASSET_ROOT = Path(__file__).parent / "assets" / "pipeline-studio"
ASSETS = {"": ("index.html", "text/html"), "baseline.excalidraw": ("baseline.excalidraw", "application/json")}
PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                               "connect-src 'none'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'",
}


def register(app, session):
    def asset_response(request, asset_path):
        if not session(request):
            raise HTTPException(status_code=403, detail="운영자 검토 화면의 세션이 필요합니다", headers=PRIVATE_HEADERS)
        asset = ASSETS.get(asset_path)
        if asset is None:
            raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다", headers=PRIVATE_HEADERS)
        filename, media_type = asset
        path = ASSET_ROOT / filename
        if path.is_symlink() or path.resolve().parent != ASSET_ROOT.resolve() or not path.is_file():
            raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다", headers=PRIVATE_HEADERS)
        return FileResponse(path, media_type=media_type, headers=PRIVATE_HEADERS)

    @app.api_route("/api/pipeline-studio", methods=["GET", "HEAD"])
    @app.api_route("/api/pipeline-studio/", methods=["GET", "HEAD"])
    def studio(request: Request):
        return asset_response(request, "")

    @app.api_route("/api/pipeline-studio/{asset_path:path}", methods=["GET", "HEAD"])
    def studio_asset(request: Request, asset_path: str):
        return asset_response(request, asset_path)
