import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from office.api import create_app
from office.store import Store
from tests.test_cards import approved_job


@pytest.fixture
def bundle(tmp_path):
    store = Store(tmp_path)
    job = approved_job(store)
    slides = []
    for index in range(1, 8):
        path = store.artifacts / f"card-{index:02d}.png"
        Image.new("RGB", (12, 16), (index * 20, 40, 70)).save(path)
        record = {"id": f"asset_card{index}", "path": path.name,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        slides.append({"index": index, "title": f"제목 {index}", "body": f"본문 {index}",
                       "artifact_id": record["id"], "artifact": record})
    cards = {"version": 3, "source_hash": job["source_hash"], "slides": slides,
             "checks": {"passed": False, "issues": ["검토할 문구"]}}
    store.update_job(job["id"], cards=cards)
    client = TestClient(create_app(store), base_url="http://localhost:8510")
    client.get("/api/session")
    url = f"/api/jobs/{job['id']}/cards/archive?version=3&source_hash={job['source_hash']}"
    return store, client, job, cards, url


def test_archive_contains_ordered_cards_and_review_status_without_changing_approval(bundle):
    store, client, job, cards, url = bundle
    before = store.job(job["id"])
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"card-{i:02d}.png" for i in range(1, 8)] + ["review.json", "README.txt"]
        review = json.loads(archive.read("review.json"))
        assert review["purpose"] == "review_only" and review["release_approved"] is False
        assert review["checks"] == cards["checks"]
        assert [s["title"] for s in review["slides"]] == [f"제목 {i}" for i in range(1, 8)]
    assert store.job(job["id"]) == before


@pytest.mark.parametrize("change", ["version", "source", "tampered", "missing", "duplicate", "order", "escape"])
def test_archive_rejects_changed_incomplete_or_unsafe_inputs(bundle, change, tmp_path):
    store, client, job, cards, url = bundle
    if change == "version":
        url = url.replace("version=3", "version=2")
    elif change == "source":
        store.update_job(job["id"], source_hash="different")
    elif change == "tampered":
        (store.artifacts / cards["slides"][0]["artifact"]["path"]).write_bytes(b"changed")
    elif change == "missing":
        cards["slides"][0]["artifact"] = None
    elif change == "duplicate":
        cards["slides"][1]["artifact"] = cards["slides"][0]["artifact"].copy()
    elif change == "order":
        cards["slides"][1]["index"] = 1
    elif change == "escape":
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"private")
        cards["slides"][0]["artifact"]["path"] = "../outside.png"
    if change not in {"version", "source", "tampered"}:
        store.update_job(job["id"], cards=cards)
    response = client.get(url)
    assert response.status_code in {404, 409}
    assert response.headers.get("content-type", "").startswith("application/json")
