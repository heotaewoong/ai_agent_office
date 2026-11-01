import test from "node:test";
import assert from "node:assert/strict";
import { feedbackMessage } from "../lib/action-feedback.ts";
test("running action remains explicit even when prior notice exists",()=>{assert.deepEqual(feedbackMessage("출고 승인","","old"),{kind:"pending",title:"출고 승인 처리 중",message:"서버 응답을 기다리고 있습니다. 중복해서 누르지 마세요."});});
test("failures are visible and do not pretend delivery succeeded",()=>{assert.equal(feedbackMessage("","작업시간 종료","")?.kind,"error");});
test("no work means no misleading activity",()=>{assert.equal(feedbackMessage("","",""),null);assert.equal(feedbackMessage("","","승인을 저장했습니다")?.kind,"success");});
