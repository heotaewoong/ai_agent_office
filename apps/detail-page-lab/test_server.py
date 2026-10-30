import base64
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import zipfile
import zlib

from server import Lab, InputError, handler, image_info, brief_input, decode_images, ThreadingHTTPServer


def png(width=1080, height=2160, color=1):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = (b"\x00" + bytes([color, 120, 180]) * width) * height
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def image(raw):
    return {"data": base64.b64encode(raw).decode()}


def body():
    return {"product": "합성 상품", "audience": "구매를 검토하는 독자", "features": "구성 파일 2개\n사용자가 입력한 사실", "rights_confirmed": True, "images": [image(png(64, 64))]}


class LabTests(unittest.TestCase):
    def test_comparison_draft_never_fabricates_human_approval(self):
        payload = body()
        payload['comparison_draft'] = True
        project = self.lab.create(payload)
        self.assertEqual(project['plan'][-1]['role'], 'FAQ')
        with zipfile.ZipFile(io.BytesIO(self.lab.bundle(project['id'], 'request'))) as z:
            self.assertIn('UNREVIEWED-DRAFT.txt', z.namelist())
            self.assertIn('unreviewed_plan', json.loads(z.read('product-brief.json')))
        result = self.lab.import_results(project['id'], {'plan_hash': project['plan_hash'], 'images': [image(png(color=i)) for i in range(1, 7)]})
        self.assertIsNone(result['plan_review'])
        self.assertIsNone(result['image_review'])
        self.assertFalse(result['published'])
        with self.assertRaises(InputError):
            self.lab.review_results(project['id'], {'result_hash': result['result_hash'], 'confirmed': True})
        with self.assertRaises(InputError):
            self.lab.bundle(project['id'], 'results')
        with zipfile.ZipFile(io.BytesIO(self.lab.bundle(project['id'], 'draft'))) as z:
            self.assertIn('UNREVIEWED-DRAFT.txt', z.namelist())
            self.assertIn('panel-06.png', z.namelist())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = Lab(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_independent_store_and_no_model_calls(self):
        old = Path(self.temp.name) / "office.sqlite3"
        old.write_bytes(b"unrelated-pipeline")
        project = self.lab.create(body())
        self.assertEqual(old.read_bytes(), b"unrelated-pipeline")
        self.assertEqual(len(project["plan"]), 6)
        self.assertFalse(self.lab.status()["image_engine_connected"])
        self.assertEqual(project["external_calls"], 0)
        self.assertTrue(project["rights_attestation"]["confirmed"])

    def test_handoff_requires_actual_review_and_current_hash(self):
        project = self.lab.create(body())
        with self.assertRaises(InputError):
            self.lab.bundle(project["id"], "request")
        for value in ({"confirmed": False, "plan_hash": project["plan_hash"]}, {"confirmed": True, "plan_hash": "old"}):
            with self.assertRaises(InputError):
                self.lab.approve(project["id"], value)
        self.lab.approve(project["id"], {"confirmed": True, "plan_hash": project["plan_hash"]})
        with zipfile.ZipFile(io.BytesIO(self.lab.bundle(project["id"], "request"))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("HOST-REQUEST.md", archive.namelist())
            self.assertIn("ASSET_LICENSE_MANIFEST.md", archive.namelist())
            self.assertNotIn("auth.json", archive.namelist())

    def test_edit_invalidates_review_and_stale_edit_is_rejected(self):
        project = self.lab.create(body())
        self.lab.approve(project["id"], {"confirmed": True, "plan_hash": project["plan_hash"]})
        panels = [{"headline": "확인한 새 제목", "copy": "검토할 새 문구"} for _ in range(6)]
        changed = self.lab.edit_plan(project["id"], {"plan_hash": project["plan_hash"], "panels": panels})
        self.assertNotEqual(changed["plan_hash"], project["plan_hash"])
        self.assertIsNone(changed["plan_review"])
        with self.assertRaises(InputError):
            self.lab.edit_plan(project["id"], {"plan_hash": project["plan_hash"], "panels": panels})

    def test_images_size_duplicates_and_corruption(self):
        sample = png(64, 64)
        info = image_info(sample)
        self.assertEqual(info["width"], 64)
        for raw in (b"<svg><script/></svg>", sample[:-1], sample[:50] + b"broken" + sample[56:]):
            with self.assertRaises(InputError):
                image_info(raw)
        with self.assertRaises(InputError):
            decode_images([image(sample), image(sample)])
        with self.assertRaises(InputError):
            decode_images([image(sample)] * 6, results=True)

    def test_rights_and_fields_required(self):
        for patch in ({"rights_confirmed": False}, {"product": ""}, {"features": ""}, {"product": "x" * 121}):
            with self.assertRaises(InputError):
                brief_input({**body(), **patch})

    def test_results_review_zip_and_no_overwrite(self):
        project = self.lab.create(body())
        self.lab.approve(project["id"], {"confirmed": True, "plan_hash": project["plan_hash"]})
        pictures = [image(png(color=i)) for i in range(1, 7)]
        result = self.lab.import_results(project["id"], {"plan_hash": project["plan_hash"], "images": pictures})
        with self.assertRaises(InputError):
            self.lab.import_results(project["id"], {"plan_hash": project["plan_hash"], "images": pictures})
        with self.assertRaises(InputError):
            self.lab.bundle(project["id"], "results")
        self.lab.review_results(project["id"], {"confirmed": True, "result_hash": result["result_hash"]})
        with zipfile.ZipFile(io.BytesIO(self.lab.bundle(project["id"], "results"))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len([n for n in archive.namelist() if n.startswith("panel-")]), 6)
            self.assertFalse(json.loads(archive.read("review.json"))["published"])

    def test_asset_tampering_and_path_traversal(self):
        project = self.lab.create(body())
        with self.assertRaises(InputError):
            self.lab.read("../../office")
        with self.assertRaises(FileNotFoundError):
            self.lab.asset(project["id"], "../office.sqlite3")
        (self.lab.folder(project["id"]) / project["references"][0]["name"]).write_bytes(b"tampered")
        with self.assertRaises(InputError):
            self.lab.asset(project["id"], project["references"][0]["name"])

    def test_http_origin_csp_and_private_responses(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.lab, "https://office.example"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/api/status")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn("no-store", response.getheader("Cache-Control"))
            self.assertIn("object-src 'none'", response.getheader("Content-Security-Policy"))
            response.read()
            data = json.dumps(body())
            connection.request("POST", "/api/projects", data, {"Content-Type": "application/json", "Origin": "https://evil.example"})
            self.assertEqual(connection.getresponse().status, 403)
            connection.close()
            connection = HTTPConnection(*server.server_address)
            connection.request("POST", "/api/projects", data, {"Content-Type": "application/json", "Origin": "https://office.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["state"], "plan_review")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
