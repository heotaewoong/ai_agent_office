import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
import {formatBytes} from "../lib/workflow.ts";
const nativeRequire=createRequire(import.meta.url);
const source=readFileSync(new URL("../app/editorial-assets-panel.tsx",import.meta.url),"utf8");
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const module={exports:{} as any};
Function("require","exports",compiled)((name:string)=>name==="../lib/workflow"?{formatBytes}:name==="./external-media-panel"?{ExternalMediaPanel:()=>null}:nativeRequire(name),module.exports);
const Panel=module.exports.EditorialAssetsPanel;
function nodes(tree:any):any[]{return Array.isArray(tree)?tree.flatMap(nodes):tree?.props?[tree,...nodes(tree.props.children)]:[];}
const job={id:"job-test",source_hash:"current",drafts:[{id:"draft-test",title:"검토본",body:"원고",source_hash_snapshot:"current",assets:[{name:"instagram-caption-review.txt",size:1200,media_type:"text/plain",sha256:"a"}]}]};
test("긴 파일명은 보조 정보로 두고 의미 있는 다운로드 이름과 접힌 미리보기를 제공한다",()=>{
 const list=nodes(Panel({job}));
 const preview=list.find(n=>n.props.className==="editorial-preview");
 assert.ok(preview);assert.notEqual(preview.props.open,true);
 const link=list.find(n=>n.props.download===true);
 assert.equal(link.props["aria-label"],"인스타그램 게시 문구 내려받기");
 assert.match(link.props.href,/drafts\/draft-test\/files\/instagram-caption-review.txt$/);
 assert.ok(list.some(n=>n.props.href==="/scripts/job-test"));
});
test("편집 화면의 불러오기는 승인이나 저장 없이 콜백만 호출하며 잠금 상태를 따른다",()=>{
 const loaded:any[]=[];
 const list=nodes(Panel({job,onLoadDraft:(draft:any)=>loaded.push(draft),editLocked:true}));
 const button=list.find(n=>n.type==="button");assert.equal(button.props.disabled,true);
 const enabled=nodes(Panel({job,onLoadDraft:(draft:any)=>loaded.push(draft)})).find(n=>n.type==="button");
 enabled.props.onClick();assert.deepEqual(loaded,[job.drafts[0]]);
});
