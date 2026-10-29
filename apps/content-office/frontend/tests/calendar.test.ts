import test from "node:test";
import assert from "node:assert/strict";
import { calendarSourceUrl, calendarTimeliness, dDayLabel, isVerifiedExam, timelinessPercent } from "../lib/calendar.ts";

const confirmed = { verified: true, source_url: "https://www.q-net.or.kr/" };

test("다음 시험이 있으면 'D-일수' 배지를 만든다", () => {
  assert.equal(dDayLabel({ ...confirmed, name: "정보처리기사 필기", date: "2026-11-30", days_left: 32 }), "정보처리기사 필기 D-32");
  assert.equal(dDayLabel({ ...confirmed, name: "오픽", date: "2026-10-29", days_left: 0 }), "오픽 D-Day");
  assert.equal(dDayLabel({ ...confirmed, name: "오픽", date: "2026-10-26", days_left: -3 }), "오픽 D+3");
});

test("다음 시험이 없으면 빈 문자열", () => {
  assert.equal(dDayLabel(null), "");
  assert.equal(dDayLabel(undefined), "");
  assert.equal(dDayLabel({ ...confirmed, name: "", date: "2026-11-30", days_left: 10 }), "D-10");
});

test("미확인 추정 편입 일정은 D-day와 85% 막대 대신 확인 안내를 보낸다", () => {
  const estimate = { name: "편입 접수 예상", date: "2026-12-28", days_left: 59, verified: false, source_url: "", note: "추정이며 대학별 공고 확인 필요" };
  assert.match(dDayLabel(estimate), /미확인 추정 시기.*공식 공고·모집요강 확인/);
  assert.ok(!dDayLabel(estimate).includes("D-59"));
  assert.equal(calendarTimeliness(estimate, 0.85), null);
  assert.equal(calendarTimeliness({ ...estimate, verified: true }, 0.85), null);
  assert.equal(calendarTimeliness(null, 0.65), null);
});

test("확인 bool과 공개 HTTPS 출처를 함께 가진 동일 일정만 시의성을 표시한다", () => {
  const exam = { ...confirmed, name: "기록된 일정", date: "2026-11-30", days_left: 32 };
  assert.equal(isVerifiedExam(exam), true);
  assert.equal(calendarSourceUrl(exam), confirmed.source_url);
  assert.equal(calendarTimeliness(exam, 0.85), 85);
  for (const verified of [false, undefined, "true", "false"])
    assert.equal(isVerifiedExam({ ...exam, verified } as never), false);
  assert.equal(calendarTimeliness(exam, Number.NaN), null);
});

test("달력 출처는 인증정보·공백·비HTTPS·로컬 링크를 열지 않는다", () => {
  const exam = { ...confirmed, name: "기록", date: "2026-11-30", days_left: 32 };
  for (const source_url of ["", "http://www.q-net.or.kr/", "https://localhost/", "https://127.0.0.1/", "https://10.0.0.1/", "https://service.internal/", "https://user:pass@www.q-net.or.kr/", " https://www.q-net.or.kr/", "broken"]) {
    assert.equal(calendarSourceUrl({ ...exam, source_url }), null, source_url);
    assert.equal(isVerifiedExam({ ...exam, source_url }), false, source_url);
  }
});

test("시의성 0~1을 0~100 정수로 바꾸고 범위를 벗어나면 자른다", () => {
  assert.equal(timelinessPercent(0.5), 50);
  assert.equal(timelinessPercent(1.2), 100);
  assert.equal(timelinessPercent(-1), 0);
  assert.equal(timelinessPercent(undefined), 0);
  assert.equal(timelinessPercent(Number.NaN), 0);
});
