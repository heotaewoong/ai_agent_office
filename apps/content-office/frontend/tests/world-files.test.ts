import test from "node:test";
import assert from "node:assert/strict";
import { resolveWorldFile } from "../lib/world-files.ts";
const root = "/srv/world";
test("빈 경로는 index.html", () => assert.deepEqual(resolveWorldFile(root, undefined), { path: "/srv/world/index.html", type: "text/html; charset=utf-8" }));
test("확장자별 타입", () => {
  assert.equal(resolveWorldFile(root, ["styles.css"])?.type, "text/css; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["app.js"])?.type, "text/javascript; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["data", "space.json"])?.type, "application/json; charset=utf-8");
});
test("상위 경로·알 수 없는 확장자는 거부", () => {
  assert.equal(resolveWorldFile(root, ["..", "secret.md"]), null);
  assert.equal(resolveWorldFile(root, ["README.md"]), null);
  assert.equal(resolveWorldFile(root, ["a/../../x.html"]), null);
});
