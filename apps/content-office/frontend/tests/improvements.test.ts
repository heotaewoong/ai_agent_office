import test from "node:test";
import assert from "node:assert/strict";
import {workspaceIsCurrent, reviewBinding, type ImprovementWorkspace} from "../lib/improvements.ts";
import {briefOverridesFromForm, briefFormFromBrief} from "../lib/briefs.ts";

test("feedback remains bound to the selected job and source",()=>{
  const workspace={job_id:"job_one",source_hash:"version"} as ImprovementWorkspace;
  assert.equal(workspaceIsCurrent(workspace,"job_one","version"),true);
  assert.equal(workspaceIsCurrent(workspace,"job_other","version"),false);
  assert.equal(workspaceIsCurrent(workspace,"job_one","new"),false);
  assert.equal(workspaceIsCurrent({...workspace,source_hash:null},"job_one",null),false);
});
test("current alternative and content goal survive form handoff",()=>{
  assert.deepEqual(briefOverridesFromForm({brief_current_solution:"  수동 검색  ",brief_goal:"연결 상태 구별"}),{overrides:{current_solution:"수동 검색",goal:"연결 상태 구별"}});
  assert.equal(briefFormFromBrief(undefined).brief_current_solution,"");
});
test("changed production or quiz does not silently rebind old review form",()=>{
  const job={source_hash:"same",quiz:{version:1,generated_at:"first"}};
  assert.notEqual(reviewBinding(job),reviewBinding({...job,quiz:{...job.quiz!,version:2}}));
  assert.notEqual(reviewBinding(job),reviewBinding({...job,manifest:{hash:"new",files:[]}}));
});
