import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const html=readFileSync(new URL("../../backend/office/assets/pipeline-studio/index.html",import.meta.url),"utf8");
const sourceHash="synthetic-pipeline-source";
const fresh=()=>({schemaVersion:1,sourceHash,edits:{},nodes:[],edges:[]});
const clone=<T>(value:T):T=>JSON.parse(JSON.stringify(value));

function between(start:string,end:string) {
  const from=html.indexOf(start),to=html.indexOf(end,from);
  assert.ok(from>=0 && to>from,"Editor function boundaries missing: "+start);
  return html.slice(from,to);
}

function editor(initial:any=fresh()) {
  const elements:Record<string,any>={
    "#editor-label":{value:"수정 문구"},"#editor-note":{value:"검토 메모"},
    "#editor-message":{textContent:""},
  };
  const writes:string[]=[];
  let failStorage=false,selectionCalls=0;
  const ctx:Record<string,any>={
    sourceHash,storageKey:"synthetic-storage-key",fresh,clone,
    rowById:new Map([["source_1",{original_id:"source_1",containerId:"shape_1"}]]),
    baseById:new Map([["source_1",{}],["shape_1",{}]]),rows:[{original_id:"source_1"}],
    state:clone(initial),history:[clone(initial)],position:0,activeId:"source_1",box:[0,0,1000,1000],
    crypto:{randomUUID:()=>"synthetic-new-node"},
    q:(selector:string)=>elements[selector] ??= {},
    render(){},syncForm(){},select(){selectionCalls++;},
    localStorage:{setItem(_key:string,value:string){if(failStorage)throw Error("QuotaExceededError");writes.push(value);}},
  };
  vm.createContext(ctx);
  vm.runInContext(
    between("  let storageWarning = ''","  function validate(value)")+
    between("  function validate(value) {","  try {const saved = localStorage")+
    between("  function persist()","  function memberIds"),ctx);
  for(const selector of ["#editor-apply","#editor-add","#editor-save"]) {
    const line=html.split(/\r?\n/).find(value=>value.includes("q('"+selector+"').onclick="));
    assert.ok(line,"Editor action missing: "+selector);
    vm.runInContext(line,ctx);
  }
  return {ctx,writes,elements,failStorage(value:boolean){failStorage=value;},selectionCalls:()=>selectionCalls};
}

function plans(count:number) {
  const state:any=fresh();
  state.nodes=Array.from({length:count},(_,i)=>({id:"plan_"+i,label:"합성 계획",note:"",x:0,y:0,width:280,height:150}));
  return state;
}

test("저장이 거부되면 적용 후에도 경고를 유지하고 실제 저장 성공 때만 해제한다",()=>{
  const subject=editor();
  subject.failStorage(true);
  subject.elements["#editor-apply"].onclick();
  assert.match(subject.elements["#editor-message"].textContent,/브라우저 저장 실패/);
  assert.equal(subject.writes.length,0);
  assert.equal(subject.ctx.state.edits.source_1.label,"수정 문구");
  subject.elements["#editor-save"].onclick();
  assert.match(subject.elements["#editor-message"].textContent,/브라우저 저장 실패/);
  subject.failStorage(false);
  subject.elements["#editor-save"].onclick();
  assert.doesNotMatch(subject.elements["#editor-message"].textContent,/브라우저 저장 실패/);
  assert.equal(JSON.parse(subject.writes.at(-1)!).edits.source_1.label,"수정 문구");
});

test("500개 계획에서 추가를 거부하고 기존 편집본과 이력을 보존한다",()=>{
  const subject=editor(plans(500));
  const before=JSON.stringify(subject.ctx.state);
  subject.elements["#editor-add"].onclick();
  assert.equal(JSON.stringify(subject.ctx.state),before);
  assert.equal(subject.ctx.history.length,1);
  assert.equal(subject.writes.length,0);
  assert.equal(subject.selectionCalls(),0);
  assert.match(subject.elements["#editor-message"].textContent,/변경하지 않았습니다.*항목 수 초과/);
});

test("1501번째 연결선도 저장하지 않고 마지막 정상 편집본을 유지한다",()=>{
  const initial=plans(2);
  initial.edges=Array.from({length:1500},(_,i)=>({id:"plan_edge_"+i,from:"plan_0",to:"plan_1"}));
  const subject=editor(initial),next=clone(initial);
  next.edges.push({id:"plan_edge_overflow",from:"plan_0",to:"plan_1"});
  assert.equal(subject.ctx.commit(next),false);
  assert.equal(JSON.stringify(subject.ctx.state),JSON.stringify(initial));
  assert.equal(subject.writes.length,0);
});

test("드래그가 허용 좌표를 벗어나면 메모리 상태도 마지막 정상 이력으로 복구한다",()=>{
  const initial=plans(1),subject=editor(initial);
  subject.ctx.state.nodes[0].x=1_000_001;
  assert.equal(subject.ctx.commit(),false);
  assert.equal(JSON.stringify(subject.ctx.state),JSON.stringify(initial));
  assert.equal(subject.ctx.history.length,1);
  assert.equal(subject.writes.length,0);
  assert.match(subject.elements["#editor-message"].textContent,/좌표 오류/);
});
