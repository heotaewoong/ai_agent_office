"""Synthetic HTTP fixtures plus consistency checks of the packaged private drawing."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from office.api import create_app
from office.store import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("OFFICE_PUBLIC_ORIGIN", raising=False)
    return TestClient(create_app(Store(tmp_path / "state")), base_url="http://localhost:8510")


@pytest.fixture
def assets(tmp_path, monkeypatch):
    from office import api_pipeline_studio
    root = tmp_path / "private-assets"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>Synthetic studio</title>", encoding="utf-8")
    (root / "baseline.excalidraw").write_text('{"type":"excalidraw","elements":[]}', encoding="utf-8")
    (root / "secret.txt").write_text("must not be served", encoding="utf-8")
    monkeypatch.setattr(api_pipeline_studio, "ASSET_ROOT", root)
    return root


def authenticate(client):
    token = client.get("/api/session").json()["csrf"]
    return {"Origin": "http://localhost:3110", "X-Office-CSRF": token}


@pytest.mark.parametrize("path", ["/api/pipeline-studio/", "/api/pipeline-studio/baseline.excalidraw"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_private_assets_require_existing_signed_session(client, path, method):
    response = client.request(method, path)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    client.cookies.set("hb_office_session", "forged.0.signature")
    assert client.request(method, path).status_code == 403


@pytest.mark.parametrize("name,media_type", [("", "text/html"), ("baseline.excalidraw", "application/json")])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_authenticated_get_and_head_serve_only_fixed_assets(client, assets, name, media_type, method):
    authenticate(client)
    response = client.request(method, "/api/pipeline-studio/" + name)
    assert response.status_code == 200
    expected = (assets / (name or "index.html")).read_bytes()
    assert response.content == (expected if method == "GET" else b"")
    assert int(response.headers["content-length"]) == len(expected)
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    directives = response.headers["content-security-policy"].split("; ")
    for directive in ("default-src 'self'", "script-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline'",
                      "connect-src 'none'", "frame-ancestors 'self'", "object-src 'none'", "base-uri 'none'"):
        assert directive in directives


@pytest.mark.parametrize("path", ["index.html", "secret.txt", "../api.py", "%2e%2e/api.py",
                                   "%2e%2e%2fapi.py", "..%5capi.py", "nested/baseline.excalidraw",
                                   "baseline.excalidraw/extra", "%00baseline.excalidraw"])
def test_arbitrary_and_traversal_paths_are_not_served(client, assets, path):
    authenticate(client)
    response = client.get("/api/pipeline-studio/" + path)
    assert response.status_code == 404
    assert b"must not be served" not in response.content


@pytest.mark.parametrize("name", ["index.html", "baseline.excalidraw"])
def test_missing_file_returns_private_404(client, assets, name):
    authenticate(client)
    (assets / name).unlink()
    response = client.get("/api/pipeline-studio/" + ("" if name == "index.html" else name))
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert str(assets) not in response.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_studio_is_read_only_and_preserves_csrf_guard(client, assets, method):
    before = {p.name: p.read_bytes() for p in assets.iterdir()}
    assert client.request(method, "/api/pipeline-studio/").status_code == 403
    headers = authenticate(client)
    response = client.request(method, "/api/pipeline-studio/", headers=headers)
    assert response.status_code == 405
    assert set(response.headers["allow"].replace(" ", "").split(",")) == {"GET", "HEAD"}
    assert {p.name: p.read_bytes() for p in assets.iterdir()} == before


def test_foreign_origin_cannot_read_with_valid_cookie(client, assets):
    authenticate(client)
    assert client.get("/api/pipeline-studio/", headers={"Origin": "https://attacker.example"}).status_code == 403


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_studio_without_trailing_slash_keeps_origin_without_redirect(client, assets, method):
    path = "/api/pipeline-studio"
    assert client.request(method, path, follow_redirects=False).status_code == 403
    authenticate(client)
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 200 and "location" not in response.headers
    assert response.content == ((assets / "index.html").read_bytes() if method == "GET" else b"")


@pytest.fixture(scope="module")
def packaged_studio():
    root = Path(__file__).resolve().parents[1] / "office" / "assets" / "pipeline-studio"
    html = (root / "index.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "Standalone studio must include its data without a network request"
    return html, json.loads(match[1]), json.loads((root / "baseline.excalidraw").read_text(encoding="utf-8"))


def test_packaged_rows_cover_every_original_label_and_preserve_original_geometry(packaged_studio):
    _, data, baseline = packaged_studio
    rows = data["rows"]
    original = {e["id"][len("original_"):]: e for e in baseline["elements"] if e["id"].startswith("original_")}
    edited = {e["id"]: e for e in data["editScene"]["elements"]}
    assert len(rows) == len({r["original_id"] for r in rows}) == 124
    assert {r["number"] for r in rows} == set(range(1, 125))
    assert {r["original_index"] for r in rows} == set(range(124))
    assert len(original) == 344 and set(original) == set(data["bounds"])
    assert {r["original_id"] for r in rows} == {identity for identity, e in original.items() if e["type"] == "text"}
    for identity, element in original.items():
        assert [element[key] for key in ("x", "y", "width", "height")] == pytest.approx(data["bounds"][identity])
    for row in rows:
        assert original[row["original_id"]]["text"] == row["text"]
        assert original[row["original_id"]]["x"] == row["x"]
        assert original[row["original_id"]]["y"] == row["y"]
        assert edited[row["original_id"]]["originalText"] == row["current_label"]
        assert row["status"] in data["palette"]


@pytest.mark.parametrize("which", ["edit", "baseline"])
def test_packaged_native_bindings_are_complete_and_reciprocal(packaged_studio, which):
    _, data, baseline = packaged_studio
    elements = (data["editScene"] if which == "edit" else baseline)["elements"]
    by_id = {e["id"]: e for e in elements}
    assert len(by_id) == len(elements), "Duplicate IDs break native editing bindings"
    for element in elements:
        for key in ("frameId", "containerId"):
            if element.get(key):
                assert element[key] in by_id, (element["id"], key)
        for bound in element.get("boundElements") or []:
            assert bound["id"] in by_id, (element["id"], bound)
        targets = [element[key]["elementId"] for key in ("startBinding", "endBinding") if element.get(key)]
        if element["type"] == "text" and element.get("containerId"):
            targets.append(element["containerId"])
        for target in targets:
            assert target in by_id, (element["id"], target)
            assert any(bound["id"] == element["id"] for bound in by_id[target].get("boundElements") or []), (element["id"], target)


def test_packaged_svg_connectors_remain_unfilled_and_include_every_scene_element(packaged_studio):
    html, data, _ = packaged_studio
    svgs = [ET.fromstring(svg) for svg in re.findall(r"<svg\b.*?</svg>", html, re.S)]
    assert len(svgs) >= 2
    ns = {"s": "http://www.w3.org/2000/svg"}
    expected_ids = [set(data["bounds"]), {e["id"] for e in data["editScene"]["elements"]}]
    for root, ids in zip(svgs[:2], expected_ids):
        groups = root.findall(".//s:g[@data-element-id]", ns)
        assert len(groups) == len(ids)
        assert {group.get("data-element-id") for group in groups} == ids
        connectors = root.findall(".//s:polyline", ns)
        assert len(connectors) == 195  # 97 paths + 97 arrowheads + one tiny original stroke.
        assert all(line.get("fill") == "none" for line in connectors), "SVG default fill would create black triangles"
    assert not re.search(r"<script\b[^>]*\bsrc\s*=", html, re.I), "Standalone editor must not load remote scripts"
