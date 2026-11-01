import {readFileSync} from "node:fs";
import { test, expect, type Page } from '@playwright/test';

// Synthetic contracts: no source requests, account, approval or production writes.
async function researchHarness(page: Page, articles: Record<string, unknown>[] = []) {
  const writes: { path: string; csrf?: string; body: unknown }[] = [];
  let config = { platforms: ['youtube', 'tistory'], topic: 'AI 자동화', region: 'KR', youtube_channels: ['UCXZCJLdBC09xxGZ6gcdrc6A'] };
  const snapshot = {
    config_hash: 'a'.repeat(64), checked_at: '2026-10-30T12:00:00+00:00', method: '주제·출처 규칙 추천', paid_calls: 0,
    sources: [{id:'yt',name:'YouTube 공개 피드',state:'ok',count:1},{id:'hn',name:'HN',state:'failed',count:null}],
    recommendations: {youtube:[{id:'video',title:'AI agent 공개 영상',url:'https://www.youtube.com/watch?v=synthetic',feed_name:'YouTube 공개 피드',kind:'youtube',signals:{youtube_views:123},reason:'주제 일치 · 사실 검증은 별도'}]},
  };
  await page.route('**/api/**', async route => {
    const request=route.request(); const path=new URL(request.url()).pathname;
    let body: unknown={};
    if (request.method()!=='GET') writes.push({path,csrf:request.headers()['x-office-csrf'],body:request.postDataJSON()});
    if (path==='/api/discovery') {
      if (request.method()==='PUT') {const {expected_hash: ignored,...next}=request.postDataJSON();config=next;}
      body={config,config_hash:'a'.repeat(64),platforms:{youtube:'YouTube·Shorts',tistory:'티스토리·검색형 블로그',linkedin:'LinkedIn'},plan:{youtube:['youtube','community'],tistory:['search_trend']},window_open:false,stale:false,unconnected:['ViewStats 자동 연동 미구현'],snapshot,task:{state:'queued'}};
    } else if (path==='/api/session') body={csrf:'contract-token'};
    else if (path==='/api/dashboard') body={articles,jobs:[],feeds:[],agents:[],events:[],tasks:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed',authorized_end:'2026-10-01T00:00:00Z'},provider:{model:'gpt-5.4-mini',configured:false},knowledge:{}};
    else if (path==='/api/jobs/summaries') body={jobs:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  return writes;
}

test('게시 대상 저장은 조사만 요청하고 시간·원고·승인을 쓰지 않는다',async({page})=>{
  const writes=await researchHarness(page);
  await page.setViewportSize({width:390,height:844});await page.goto('/news?seg=ai');
  const panel=page.getByRole('region',{name:'게시할 곳에 맞춰 소식과 트렌드 조사'});
  await panel.getByRole('checkbox',{name:'LinkedIn',exact:true}).check();
  await panel.getByLabel('조사 주제',{exact:true}).fill('AI agent');
  const topic=panel.getByLabel('조사 주제',{exact:true});
  expect(await topic.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  expect((await topic.boundingBox())!.width).toBeGreaterThan(200);
  await panel.getByRole('button',{name:'선택 저장하고 자동 조사'}).click();
  await expect(panel.getByText(/설정과 조사 요청을 저장했습니다/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({path:'/api/discovery',csrf:'contract-token',body:{platforms:['youtube','tistory','linkedin'],topic:'AI agent',expected_hash:'a'.repeat(64)}});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('출처 실패와 누적 반응을 구분하고 조회만으로 업무를 쓰지 않는다',async({page})=>{
  const writes=await researchHarness(page);await page.goto('/news?seg=ai');
  const panel=page.getByRole('region',{name:'게시할 곳에 맞춰 소식과 트렌드 조사'});
  await panel.getByText('수집 출처·실패 상태 확인 (2개)',{exact:true}).click();
  await expect(panel.getByText('HN · 수집 실패',{exact:true})).toBeVisible();
  await panel.getByText('YouTube·Shorts에 맞춰 살펴볼 후보 1건',{exact:true}).click();
  await expect(panel.getByText(/누적 조회 123/)).toBeVisible();expect(writes).toEqual([]);
});


test('뉴스 점수 정렬은 분류와 기사 선택을 보존하고 API를 쓰지 않는다',async({page})=>{
 const articles=[['low',20,'ai'],['high',90,'exam'],['middle',60,'ai']].map(([id,score,segment])=>({id,score,segment,title:`후보 ${id}`,url:`https://example.com/${id}`,feed_name:'검사 출처',published_at:'2026-11-01T00:00:00Z'}));
 const writes=await researchHarness(page,articles);await page.goto('/news?seg=all');
 const titles=page.locator('.article-grid h3');await expect(titles).toHaveText(['후보 high','후보 middle','후보 low']);
 await page.getByRole('checkbox',{name:'후보 low 선택',exact:true}).check();
 await page.getByLabel('뉴스 정렬',{exact:true}).selectOption('score-asc');
 await expect(titles).toHaveText(['후보 low','후보 middle','후보 high']);
 await expect(page.getByRole('checkbox',{name:'후보 low 선택',exact:true})).toBeChecked();
 await page.getByRole('navigation',{name:'뉴스 분류'}).getByRole('link',{name:/AI·자동화/}).click();
 await expect(titles).toHaveText(['후보 low','후보 middle']);await expect(page).toHaveURL(/sort=score-asc/);
 await expect(page.getByRole('checkbox',{name:'후보 low 선택',exact:true})).toBeChecked();
 expect(writes).toEqual([]);
});

async function newsJobHarness(page:Page, ready=false) {
 const article={id:'news-one',title:'선택한 뉴스',url:'https://example.com/news',feed_name:'검사 출처',score:85,segment:'ai',published_at:'2026-11-01T00:00:00Z'};
 const old={id:'job-existing-news',title:'같은 뉴스의 오래된 작업',state:ready?'source_review':'research_ready',article,selections:{blog:true,video:true,pdf:false,cards:false},source_packet:ready?{title:'검수된 원고',body:'사용자가 읽고 승인할 원고입니다.',quality:{status:'passed',critical:false},video:{scenes:[]}}:null,source_hash:ready?'a'.repeat(64):null,tasks:[],events:[],drafts:[]};
 const recent={...old,id:'job-recent',title:'더 최근 작업',article:{...article,id:'other'}};
 let opened=ready;const writes:{path:string;body:any}[]=[];
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let body:any;
  if(req.method()!=='GET')writes.push({path,body:req.postDataJSON()});
  if(path==='/api/session')body={csrf:'synthetic-token'};
  else if(path==='/api/dashboard')body={articles:[article],jobs:[recent,old],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:opened?'open':'closed',authorized_end:opened?new Date(Date.now()+3600000).toISOString():'2026-10-01T00:00:00Z'},provider:{model:'synthetic',configured:false},knowledge:{}};
  else if(path==='/api/jobs' && req.method()==='POST')body={jobs:[old],draft_requests:[{job_id:old.id,state:'needs_window',reason:'원고 제작용 작업 시간을 열어 주세요'}]};
  else if(path===`/api/jobs/${old.id}`)body=old;
  else if(path==='/api/session/window'){opened=true;body={work_window:{status:'open'},services:{started:[],running:[],note:'synthetic'}};}
  else if(path===`/api/jobs/${old.id}/draft`)body={id:'task-synthetic',kind:'draft',state:'queued'};
  else if(path===`/api/jobs/${old.id}/production-estimate`)body={clips:{paid:false,clips:0},thumbnail_artwork:ready};
  else if(path===`/api/jobs/${old.id}/reviews/source`)body={...old,state:'production_queued'};
  else if(path==='/api/jobs/summaries')body={jobs:[recent,old]};
  else if(path==='/api/channels')body={channels:[]};
  else if(path==='/api/newsletters')body={issues:[]};
  else if(path.endsWith('/deliveries'))body={deliveries:[],youtube_configured:false};
  await route.fulfill({status:body===undefined?404:200,contentType:'application/json',body:JSON.stringify(body??{detail:'Synthetic fixture endpoint intentionally unavailable'})});
 });
 return {writes,old};
}

test('뉴스 작업 재열기는 해당 ID로 이동하고 오래된 작업도 목록 맨 위에 표시한다',async({page})=>{
 const {writes,old}=await newsJobHarness(page);await page.goto('/news?seg=all');
 await page.getByRole('checkbox',{name:'선택한 뉴스 선택',exact:true}).check();
 await page.getByRole('button',{name:'콘텐츠 작업 만들기',exact:true}).click();
 await expect(page).toHaveURL(`/scripts/${old.id}`);
 await expect(page.locator('.job-list .job-item').first()).toHaveAttribute('aria-current','page');
 await expect(page.locator('.job-list .job-item').first()).toContainText(old.title);
 await expect(page.getByRole('button',{name:'원고 생성 시작',exact:true})).toBeEnabled();
 expect(writes).toEqual([{path:'/api/jobs',body:{article_ids:['news-one'],start_draft:true}}]);
});

test('닫힌 작업 시간은 실행 확인 후에만 열고 원고를 요청하며 승인·제작을 자동 실행하지 않는다',async({page})=>{
 const {writes,old}=await newsJobHarness(page);await page.goto(`/scripts/${old.id}`);
 await page.getByRole('button',{name:'원고 생성 시작',exact:true}).click();
 const confirm=page.getByRole('region',{name:'원고 자동 생성 실행 확인'});await expect(confirm).toBeVisible();
 expect(writes).toEqual([]);
 await confirm.getByRole('button',{name:'작업 시간 열고 원고 생성',exact:true}).click();
 await expect.poll(()=>writes.map(row=>row.path)).toEqual(['/api/session/window',`/api/jobs/${old.id}/draft`]);
 expect(writes[0].body).toEqual({minutes:30});
});

test('승인① 화면에서 썸네일 비용을 확인한 뒤에만 승인·자동 제작을 함께 요청한다',async({page})=>{
 const {writes,old}=await newsJobHarness(page,true);await page.goto(`/scripts/${old.id}`);
 await page.getByRole('button',{name:'원고 승인',exact:true}).click();
 const confirm=page.getByRole('region',{name:'원고 승인 최종 확인'});
 await expect(confirm.getByText(/최대 600원 예약/)).toBeVisible();
 expect(writes).toEqual([]);
 await confirm.getByRole('button',{name:'이 원고 승인·자동 제작',exact:true}).click();
 expect(writes).toEqual([]);
 await confirm.getByRole('button',{name:'유료 포함 제작 확인',exact:true}).click();
 await expect.poll(()=>writes.length).toBe(1);
 expect(writes[0]).toEqual({path:`/api/jobs/${old.id}/reviews/source`,body:{version:old.source_hash,decision:'approved',selections:old.selections,auto_produce:true,confirm_paid_clips:true,confirm_paid_thumbnails:true}});
});

test('내 원고 등록은 주제 선택 전에는 저장하지 않고 선택한 기획을 함께 전송한다',async({page})=>{
 const {writes,old}=await newsJobHarness(page);
 await page.route('**/api/briefs',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({default:'ai-agent',presets:[{id:'transfer-admission',axis:'A',label:'대학 편입 준비',reader:'편입 영어 학습자',language:'ko'}]})}));
 await page.route('**/api/owned-source/jobs',async route=>{writes.push({path:'/api/owned-source/jobs',body:route.request().postDataJSON()});await route.fulfill({contentType:'application/json',body:JSON.stringify(old)});});
 await page.goto('/plans');
 const panel=page.getByRole('region',{name:'내 원고로 콘텐츠 만들기'});
 const body='합성 검증용 편입 학습 원고입니다. '.repeat(12);
 await panel.getByLabel('콘텐츠 제목 필수').fill('합성 편입 후기');
 await panel.getByLabel('원고·자료·만들고 싶은 내용 필수').fill(body);
 await panel.getByRole('checkbox').check();
 const save=panel.getByRole('button',{name:'내 원고로 작업실 열기'});
 await expect(save).toBeDisabled();expect(writes).toEqual([]);
 await panel.getByLabel('누구를 위한 주제인가요? · 필수').selectOption('transfer-admission');
 await save.click();
 await expect.poll(()=>writes.length).toBe(1);
 expect(writes[0].body).toEqual({title:'합성 편입 후기',body,source_url:'',owner_confirmed:true,brief_preset:'transfer-admission'});
});


test('모바일 긴 목차에서도 선택 상자와 이동 버튼이 카드 안에 남는다',async({page})=>{
 const writes=await researchHarness(page,[{id:'long',title:'긴 제목이 있는 뉴스에서 모바일 목차와 이동 버튼을 확인하는 합성 기사 제목 '.repeat(3),score:90,segment:'ai',url:'https://example.com/long',feed_name:'합성 출처',published_at:'2026-11-01T00:00:00Z'}]);
 await page.setViewportSize({width:375,height:812});await page.goto('/news?seg=all');
 const outline=page.getByRole('navigation',{name:'이 페이지 목차'});
 await expect(outline.getByRole('combobox',{name:'목차 바로 이동'})).toBeVisible();
 const bounds=await outline.evaluate(el=>{
  const box=el.getBoundingClientRect();const row=el.querySelector('.outline-select')!.getBoundingClientRect();const button=el.querySelector('button')!.getBoundingClientRect();
  return {boxRight:box.right,rowRight:row.right,buttonRight:button.right,buttonWidth:button.width};
 });
 expect(bounds.rowRight).toBeLessThanOrEqual(bounds.boxRight);
 expect(bounds.buttonRight).toBeLessThanOrEqual(bounds.boxRight);
 expect(bounds.buttonWidth).toBeGreaterThanOrEqual(44);
 expect(writes).toEqual([]);
});


test('뉴스 목차는 제목의 줄바꿈을 공백으로 읽고 PC·모바일에서 유지한다',async({page})=>{
 const writes=await researchHarness(page);await page.goto('/news?seg=all');
 const outline=page.getByRole('navigation',{name:'이 페이지 목차'});
 await expect(outline.getByRole('link',{name:/흩어진 질문과 소식이 나만의 콘텐츠가 되는 곳\./})).toBeVisible();
 await page.setViewportSize({width:375,height:812});
 await expect(outline.getByRole('combobox',{name:'목차 바로 이동'}).locator('option')).toContainText(['2. 흩어진 질문과 소식이 나만의 콘텐츠가 되는 곳.']);
 expect(writes).toEqual([]);
});

test('기획 다음 안내는 한 번만 표시하고 버튼 설명도 같은 문구에 연결한다',async({page})=>{
 const {writes}=await newsJobHarness(page);await page.goto('/plans');
 const panel=page.getByRole('region',{name:'내 원고로 콘텐츠 만들기'});
 const save=panel.getByRole('button',{name:'내 원고로 작업실 열기'});
 await expect(panel.getByText('제목을 입력해 주세요.',{exact:true})).toHaveCount(1);
 await expect(save).toHaveAccessibleDescription('제목을 입력해 주세요.');
 await expect(save).toBeDisabled();
 await page.setViewportSize({width:375,height:812});
 await panel.getByLabel('콘텐츠 제목 필수').fill('합성 UI 검사');
 const next='본문을 100자 더 적으면 다음으로 이동할 수 있어요.';
 await expect(panel.getByText(next,{exact:true})).toHaveCount(1);
 await expect(save).toHaveAccessibleDescription(next);
 await expect(save).toBeDisabled();expect(writes).toEqual([]);
});


for(const width of [375,1440]) test(`파이프라인 ${width}px 바로가기는 제목을 목차 아래에 표시하고 초점을 옮긴다`,async({page})=>{
 const writes=await researchHarness(page);
 const doc=JSON.parse(readFileSync(new URL('../../../backend/config/architecture.json',import.meta.url),'utf8'));
 await page.route('**/api/architecture',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({doc,git:{commit:null,committed_at:null,subject:null,recent:[]},build:null,build_matches_running_code:false,keys:{openai:false,gemini:false,runway:false,youtube:false},profiles:{text:'synthetic',image:'none'},window:{status:'closed'},worker:{state:'stopped'},budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},usage:[]})}));
 await page.setViewportSize({width,height:812});await page.goto('/pipeline');
 await page.getByRole('link',{name:'서버·연결 경계',exact:true}).press('Enter');
 await expect.poll(()=>page.evaluate(()=>document.getElementById('pipeline-runtime-title')!.getBoundingClientRect().top-document.querySelector('.page-outline')!.getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(0);
 await expect(page.locator('#pipeline-runtime-title')).toBeFocused();
 await expect(page).toHaveURL(/#pipeline-runtime-title$/);
 expect(writes).toEqual([]);
});

for(const width of [1440,375])test(`카드·출고함에서 ${width}px 원고 검토 위치로 복귀`,async({page})=>{
 const {writes,old}=await newsJobHarness(page,true);
 await page.setViewportSize({width,height:900});await page.goto(`/scripts/${old.id}`);
 const target=page.locator(`#studio-blog-${old.id}`);
 const body=page.getByRole('textbox',{name:'본문 · Markdown',exact:true});
 const original=await body.inputValue();
 await body.fill(original+' 저장하지 않은 검토 메모');
 const requestCount:string[]=[];page.on('request',r=>{if(r.isNavigationRequest())requestCount.push(r.url());});
 await page.getByRole('link',{name:'현재 원고 검토·승인①으로 이동',exact:true}).press('Enter');
 await expect(page).toHaveURL(new RegExp(`#studio-blog-${old.id}$`));
 await expect(target).toBeFocused();
 await expect(body).toHaveValue(original+' 저장하지 않은 검토 메모');
 expect(requestCount).toEqual([]);
 await page.getByRole('button',{name:'완성 영상 확인',exact:true}).click();
 await expect(page).toHaveURL(`/publish?job=${old.id}`);
 await page.getByRole('link',{name:'현재 원고 검토·승인①으로 이동',exact:true}).click();
 await expect(page).toHaveURL(new RegExp(`/scripts/${old.id}#studio-blog-${old.id}$`));
 await expect(target).toBeFocused();
 await expect.poll(()=>target.evaluate(el=>el.getBoundingClientRect().top-document.querySelector('.page-outline')!.getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(writes).toEqual([]);
});
