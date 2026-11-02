import {test,expect,type Page} from '@playwright/test';

async function harness(page:Page, fail=false){
 const job={id:'job-trash-test',title:'삭제 전 확인할 원고',state:'research_ready',updated_at:'2026-11-02T00:00:00Z',source_hash:null,source_packet:null,article:{id:'news',title:'선택한 뉴스',url:'https://example.com',score:80},selections:{blog:true,video:false,pdf:false,cards:false},tasks:[],events:[],drafts:[]};
 const jobs=[job],deleted=new Set<string>();const writes:string[]=[];
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let body:any,status=200;
  if(req.method()!=='GET')writes.push(path);
  if(path==='/api/session')body={csrf:'trash-test'};
  else if(path==='/api/dashboard')body={articles:[],jobs:jobs.filter(j=>!deleted.has(j.id)),feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed'},provider:{configured:false},knowledge:{}};
  else if(path==='/api/jobs/summaries')body={jobs:jobs.filter(j=>!deleted.has(j.id))};
  else if(path==='/api/trash/jobs')body={jobs:jobs.filter(j=>deleted.has(j.id)).map(j=>({...j,deleted_at:'now'}))};
  else if(path.endsWith('/trash')){if(fail){status=409;body={detail:'전송 대기 또는 확인 중인 결과가 있습니다.'};}else{const target=jobs.find(j=>path===`/api/jobs/${j.id}/trash`)!;expect(req.postDataJSON()).toEqual({expected_updated_at:target.updated_at});deleted.add(target.id);body={...target,deleted_at:'now'};}}
  else if(path.endsWith('/restore')){const target=jobs.find(j=>path===`/api/jobs/${j.id}/restore`)!;deleted.delete(target.id);body=target;}
  else if(jobs.some(j=>path===`/api/jobs/${j.id}`))body=jobs.find(j=>path===`/api/jobs/${j.id}`);
  else if(path.endsWith('/production-estimate'))body={clips:{paid:false,clips:0},thumbnail_artwork:false};
  else if(path==='/api/channels')body={channels:[]};
  else if(path.endsWith('/deliveries'))body={deliveries:[]};
  await route.fulfill({status:body===undefined?404:status,contentType:'application/json',body:JSON.stringify(body??{detail:'Synthetic endpoint intentionally unavailable'})});
 });return {job,jobs,writes};
}

for(const width of [1440,375])for(const view of ['studio','delivery'])test(`목록 ${view} ${width}px 다른 작업 삭제는 현재 원고를 열지 않고 대상만 확인한다`,async({page})=>{
 const {job,jobs,writes}=await harness(page);const other={...job,id:'job-other-trash',title:'다른 목록 원고'};jobs.push(other);
 await page.setViewportSize({width,height:1000});await page.goto(view==='studio'?`/scripts/${job.id}`:`/publish?job=${job.id}`);
 const list=page.getByRole('region',{name:'콘텐츠 작업 목록'}),trigger=list.getByRole('button',{name:`${other.title} 삭제`,exact:true});
 await trigger.click();const confirm=page.getByRole('dialog',{name:'작업 삭제 확인'});await expect(confirm).toContainText(other.title);expect(writes).toEqual([]);
 await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
 expect(page.url()).toContain(job.id);
 await trigger.click();await confirm.getByRole('button',{name:'휴지통으로 이동',exact:true}).click();
 await expect(trigger).toHaveCount(0);await expect(list.getByText(job.title,{exact:true})).toBeVisible();expect(page.url()).toContain(job.id);
 await expect(page.getByRole('button',{name:'휴지통',exact:true})).toBeFocused();
 expect(writes).toEqual([`/api/jobs/${other.id}/trash`]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

for(const width of [1440,375])for(const view of ['studio','delivery'])test(`${view} ${width}px 삭제 취소·휴지통 이동·복원`,async({page})=>{
 const {job,writes}=await harness(page);await page.setViewportSize({width,height:1000});
 await page.goto(view==='studio'?`/scripts/${job.id}`:`/publish?job=${job.id}`);
 const trigger=page.getByRole('button',{name:'작업 삭제',exact:true});await trigger.click();
 const confirm=page.getByRole('dialog',{name:'작업 삭제 확인'});await expect(confirm).toContainText(job.title);
 const box=await confirm.boundingBox();expect(box!.width).toBeLessThanOrEqual(width-30);
 expect(await confirm.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 await expect(confirm).toContainText('원본 사진·녹음');
 await page.keyboard.press('Escape');await expect(confirm).not.toBeVisible();await expect(trigger).toBeFocused();expect(writes).toEqual([]);
 await trigger.click();await confirm.getByRole('button',{name:'취소',exact:true}).click();expect(writes).toEqual([]);
 await trigger.click();await confirm.getByRole('button',{name:'휴지통으로 이동',exact:true}).click();
 await expect(page.getByRole('button',{name:'작업 삭제',exact:true})).toHaveCount(0);
 await expect(page.getByRole('region',{name:'콘텐츠 작업 목록'}).getByText(job.title,{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'휴지통',exact:true}).click();
 const trash=page.getByRole('dialog',{name:'작업 휴지통'});await expect(trash).toContainText(job.title);
 await trash.getByRole('button',{name:`${job.title} 복원`,exact:true}).click();await expect(trash).toContainText('휴지통이 비어 있습니다');
 await trash.getByRole('button',{name:'닫기',exact:true}).click();await expect(page.getByRole('button',{name:'작업 삭제',exact:true})).toBeVisible();
 expect(writes).toEqual([`/api/jobs/${job.id}/trash`,`/api/jobs/${job.id}/restore`]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('삭제 차단은 대화상자 안에 표시하고 원고와 목록을 보존한다',async({page})=>{
 const {job,writes}=await harness(page,true);await page.goto(`/scripts/${job.id}`);
 await page.getByRole('button',{name:'작업 삭제',exact:true}).click();
 const confirm=page.getByRole('dialog',{name:'작업 삭제 확인'});
 await confirm.getByRole('button',{name:'휴지통으로 이동',exact:true}).click();
 await expect(confirm.getByRole('alert')).toContainText('전송 대기');
 await expect(page.getByRole('button',{name:'작업 삭제',exact:true})).toBeVisible();expect(writes).toHaveLength(1);
});

test('진행 중 작업은 삭제 버튼을 끄고 이유를 표시한다',async({page})=>{
 const {job,writes}=await harness(page);job.state='drafting';await page.goto(`/scripts/${job.id}`);
 await expect(page.getByRole('button',{name:'작업 삭제',exact:true})).toBeDisabled();
 await expect(page.getByText('처리 중이거나 결과 불명인 작업은 운영 기록에서 결과를 확인한 뒤 삭제할 수 있습니다.')).toBeVisible();
 expect(writes).toEqual([]);
});

test('목록에서 다른 작업을 삭제해도 현재 미저장 본문을 보존하고 편집 중인 대상 삭제는 막는다',async({page})=>{
 const {job,jobs,writes}=await harness(page);
 Object.assign(job,{state:'source_review',source_hash:'b'.repeat(64),source_packet:{title:job.title,body:'기존 본문',audience:{language:'ko'},quality:{status:'passed',critical:false},evidence:[],video:{scenes:[]}}});
 const other={...job,id:'job-other-unsaved',title:'삭제할 다른 작업'};jobs.push(other);
 await page.goto(`/scripts/${job.id}`);await page.getByLabel('본문 · Markdown',{exact:true}).fill('서버에 저장하지 않은 현재 편집 내용');
 const list=page.getByRole('region',{name:'콘텐츠 작업 목록'});
 await expect(list.getByRole('button',{name:`${job.title} 삭제`,exact:true})).toBeDisabled();
 await list.getByRole('button',{name:`${other.title} 삭제`,exact:true}).click();
 await page.getByRole('dialog',{name:'작업 삭제 확인'}).getByRole('button',{name:'휴지통으로 이동',exact:true}).click();
 await expect(list.getByRole('button',{name:`${other.title} 삭제`,exact:true})).toHaveCount(0);
 await expect(page.getByLabel('본문 · Markdown',{exact:true})).toHaveValue('서버에 저장하지 않은 현재 편집 내용');
 expect(page.url()).toContain(job.id);expect(writes).toEqual([`/api/jobs/${other.id}/trash`]);
});

test('목록 삭제를 취소한 뒤 다른 화면을 왕복해도 확인창을 다시 열지 않는다',async({page})=>{
 const {job,writes}=await harness(page);await page.goto(`/scripts/${job.id}`);
 await page.getByRole('region',{name:'콘텐츠 작업 목록'}).getByRole('button',{name:`${job.title} 삭제`,exact:true}).click();
 await page.getByRole('dialog',{name:'작업 삭제 확인'}).getByRole('button',{name:'취소',exact:true}).click();
 const nav=page.getByRole('navigation',{name:'오피스 메뉴'});
 await nav.getByRole('link',{name:'오늘의 뉴스',exact:true}).click();
 await expect(page).toHaveURL(/\/news/);
 await nav.getByRole('link',{name:/콘텐츠 작업실/}).click();
 await expect(page.getByRole('region',{name:'콘텐츠 작업 목록'})).toBeVisible();
 await expect(page.getByRole('dialog',{name:'작업 삭제 확인'})).not.toBeVisible();expect(writes).toEqual([]);
});
