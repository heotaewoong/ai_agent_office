import test from "node:test";
import assert from "node:assert/strict";
import { clock, frameNote, parseAt } from "../lib/frame-pick.ts";

test("시각은 초나 분:초로 받고 틀린 형식은 막는다", () => {
  assert.equal(parseAt("75"), 75);
  assert.equal(parseAt(" 1:15 "), 75);
  assert.equal(parseAt("01:02:03"), 3723);
  assert.equal(parseAt("0:03.5"), 3.5);
  for (const bad of ["", "1:75", "abc", "-3", "1:2", "10:61:00", "99999"]) assert.equal(parseAt(bad), null, bad);
  assert.equal(clock(75.4), "1:15");
});

test("내 영상 장면 후보는 시각, 자른 방법, 0원을 보여 준다", () => {
  assert.equal(frameNote(undefined), null);
  assert.equal(frameNote({ provider: "openai" }), null);
  assert.equal(frameNote({ kind: "owner_video_frame", t: 75, requested_at: 75.2, crop_by: "opencv", cost_krw: 0 }), "내 영상 1:15 · 얼굴을 찾아 오른쪽에 둠 · 0원");
  const moved = frameNote({ kind: "owner_video_frame", t: 76.1, requested_at: 75, crop_by: "center" });
  assert.ok(moved?.includes("요청 1:15 근처에서 더 선명한 장면") && moved.includes("가운데를 지킴"));
});
