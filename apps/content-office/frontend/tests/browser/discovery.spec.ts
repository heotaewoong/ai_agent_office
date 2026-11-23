import {readFileSync} from "node:fs";
import { test, expect, type Page } from '@playwright/test';

// Synthetic contracts: no source requests, account, approval or production writes.
async function researchHarness(page: Page, articles: Record<string, unknown>[] = [], stale = false) {
  const writes: { path: string; csrf?: string; body: unknown }[] = [];
  const platformSnapshotHash = 'c'.repeat(64);
  const evidenceId = 'd'.repeat(64);
  const platformIdea = {
    id: 'idea-platform-example', title: '정기 검색 영상', state: 'candidate', score: 0, reasons: [],
    outlier_band: 'unknown', blocked: ['1차 출처 없음'], edit_hash: 'e'.repeat(64),
    platform_origin: { platform: 'youtube', url: 'https://www.youtube.com/watch?v=synthetic', title: '정기 검색 영상', summary: '정기 수집 결과', observed_at: null },
    public_evidence: [{ id: evidenceId, url: 'https://example.org/official-update', title: '공식 업데이트', paragraph: 2, quote: '공식 원문의 두 번째 문단입니다.' }],
    public_discovery: { status: 'insufficient', claims: [{ label: '공식 발표의 변경점', evidence_ids: [evidenceId] }, { label: '요금 변경', evidence_ids: [] }], checked_at: '2026-10-30T12:00:00Z', paid_calls: 0 },
  };
  let platformIdeaSaved = false;
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
      body={config,config_hash:'a'.repeat(64),platforms:{youtube:'YouTube·Shorts',tistory:'티스토리·검색형 블로그',linkedin:'LinkedIn'},plan:{youtube:['youtube','community'],tistory:['search_trend']},window_open:false,stale,unconnected:['ViewStats 자동 연동 미구현'],snapshot,task:{state:'queued'}};
    } else if (path==='/api/platform-news') body={
      checked_at:'2026-10-30T12:00:00Z',snapshot_hash:platformSnapshotHash,topic:'AI 자동화',region:'KR',
      platforms:[
        {id:'youtube',label:'YouTube',source_status:'available',method:'YouTube Data API',ranking_basis:'검색 표본 누적 조회수',criteria:{kind:'popularity',metric:'views',published_days:7,observation_days:7,reference_days:30,source:'youtube_api',scope:'한국·주제 검색 표본'},reference_items:[{id:'reference-video',title:'발행일 미확인 영상',url:'https://www.youtube.com/watch?v=reference',source:'예시 계정',published_at:null,summary:'이전 수집 결과',metrics:{views:5000},observed_at:null,reference_reason:'발행일을 확인하지 못했습니다.'}],items:[{id:'sample-video',title:'정기 검색 영상',url:'https://www.youtube.com/watch?v=synthetic',source:'예시 크리에이터',published_at:null,summary:'정기 수집 결과',metrics:{views:1250},observed_at:null}]},
        {id:'instagram',label:'Instagram',source_status:'observed',method:'공개 게시물',message:'공개 반응만 표시합니다.',items:[{id:'sample-post',title:'인스타 공개 후보',url:'https://www.instagram.com/p/example/',source:'예시 계정',published_at:null,summary:'공개 게시물 표본',metrics:{likes:0,comments:50},metric_precision:{comments:'approximate'},observed_at:null}]},
        {id:'naver_blog',label:'네이버 블로그',source_status:'available',criteria:{kind:'latest',metric:null,published_days:7,observation_days:7,reference_days:30,source:'public_rss',scope:'등록 블로그 표본'},items:[]},
        {id:'linkedin',label:'LinkedIn',source_status:'waiting',method:'공개 게시물',message:'확인된 게시물이 없습니다.',items:[]},
      ],
    };
    else if (path==='/api/platform-news/ideas' && request.method()==='POST') {
      body = { idea: platformIdeaSaved ? platformIdea : {
        ...platformIdea, public_evidence: [], public_discovery: { ...platformIdea.public_discovery, claims: [], status: 'unavailable' },
      } };
      platformIdeaSaved = true;
    }
    else if (path==='/api/ideas') body={ideas:platformIdeaSaved ? [platformIdea] : []};
    else if (path==='/api/benchmarks') body={registry:{sources:[]},registry_hash:'b'.repeat(64),fields:[],platforms:{},items:[],sources_status:[],ideas:[],window_open:false};
    else if (path==='/api/questions') body={questions:[],groups:[]};
    else if (path==='/api/channels') body={channels:[]};
    else if (path==='/api/briefs') body={default:'',presets:[]};
    else if (path==='/api/session') body={csrf:'contract-token'};
    else if (path==='/api/dashboard') body={articles,jobs:[],feeds:[],agents:[],events:[],tasks:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed',authorized_end:'2026-10-01T00:00:00Z'},provider:{model:'gpt-5.4-mini',configured:false},knowledge:{}};
    else if (path==='/api/jobs/summaries') body={jobs:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  return writes;
}

test('플랫폼 소재 저장은 원문 근거 검토로 연결하고 승인과 제작을 시작하지 않는다', async ({ page }) => {
  const writes = await researchHarness(page);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/news?tab=platforms');
  const youtube = page.getByRole('region', { name: 'YouTube 공개 후보' });
  await expect(writes).toEqual([]);
  await youtube.getByRole('button', { name: '정기 검색 영상 기획 후보로 저장' }).click();
  await expect(youtube.getByText('기획 후보에 저장됨 · 공개 원문 조회 일시 지연')).toBeVisible();
  await expect(youtube.getByRole('link', { name: '저장한 후보에서 근거 검토' })).toBeVisible();
  await youtube.getByRole('button', { name: '정기 검색 영상 공개 원문 다시 찾기' }).click();
  await expect(youtube.getByText('기획 후보에 저장됨 · 원문 근거 보완 필요')).toBeVisible();
  await youtube.getByRole('link', { name: '저장한 후보에서 근거 검토' }).click();
  await expect(page).toHaveURL(/\/plans#idea-platform-example$/);
  const idea = page.locator('#idea-platform-example');
  await expect(idea).toBeFocused();
  await expect(idea).toBeInViewport();
  await expect(idea.getByText('공식 발표의 변경점', { exact: true })).toBeVisible();
  await expect(idea.getByText('요금 변경 · 원문 근거 확인 필요')).toBeVisible();
  await expect(idea.getByText('공식 원문의 두 번째 문단입니다.')).toBeVisible();
  await expect(idea.getByRole('checkbox', { name: '공식 업데이트 · 문단 2' })).not.toBeChecked();
  await expect(idea.getByRole('button', { name: '이 기획으로 작업 만들기' })).toBeDisabled();
  const save = {
    path: '/api/platform-news/ideas', csrf: 'contract-token',
    body: { platform: 'youtube', url: 'https://www.youtube.com/watch?v=synthetic', expected_hash: 'c'.repeat(64) },
  };
  expect(writes).toEqual([save, save]);
});

for(const width of [1440,390])test(`뉴스 후보를 9건씩 늘려도 선택과 작업 버튼에 바로 접근한다 ${width}px`,async({page})=>{
 const rows=Array.from({length:31},(_,i)=>({id:'browse-'+i,title:`뉴스 후보 ${String(i+1).padStart(2,'0')}`,summary:'공식 원문 설명입니다. '.repeat(12),url:`https://example.org/news/${i}`,feed_name:'공식 피드',published_at:new Date().toISOString(),segment:'ai',source_readable:true,score:100-i,score_reasons:['공식 출처']}));
 const writes=await researchHarness(page,rows);
 await page.setViewportSize({width,height:900});await page.goto('/news?seg=ai');
 const cards=page.locator('.article-grid .article-card');await expect(cards).toHaveCount(9);
 await page.getByRole('button',{name:'후보 9건 더 살펴보기',exact:true}).focus();await page.keyboard.press('Enter');await expect(cards).toHaveCount(18);await expect(cards.nth(9)).toBeFocused();
 await page.getByRole('checkbox',{name:'뉴스 후보 10 선택',exact:true}).check();
 const dock=page.getByRole('region',{name:'뉴스 선택과 작업 만들기'});
 await dock.getByRole('checkbox',{name:'뉴스 원고 자동 생성'}).uncheck();
 const create=dock.getByRole('button',{name:'콘텐츠 작업 만들기',exact:true});await expect(create).toBeEnabled();
 await cards.nth(10).scrollIntoViewIfNeeded();
 const box=await create.boundingBox();expect(box!.y).toBeGreaterThanOrEqual(0);expect(box!.y+box!.height).toBeLessThanOrEqual(900);
 if(process.env.OFFICE_UI_CAPTURE_PREFIX)await page.screenshot({path:`${process.env.OFFICE_UI_CAPTURE_PREFIX}_${width}_PRIVATE.png`});
 await page.getByRole('button',{name:/남은 13건 모두 보기/}).click();await expect(cards).toHaveCount(31);
 await expect(dock).toContainText('1개의 뉴스를 골랐어요');await expect(dock.getByRole('checkbox',{name:'뉴스 원고 자동 생성'})).not.toBeChecked();
 await page.getByRole('button',{name:'주요 뉴스 9건만 보기',exact:true}).click();await expect(cards).toHaveCount(9);await expect(dock).toContainText('1개의 뉴스를 골랐어요');
 await page.getByRole('button',{name:'후보 9건 더 살펴보기',exact:true}).click();await expect(page.getByRole('checkbox',{name:'뉴스 후보 10 선택',exact:true})).toBeChecked();
 await page.getByRole('button',{name:'후보 9건 더 살펴보기',exact:true}).click();await expect(cards).toHaveCount(27);
 await page.getByRole('button',{name:'후보 4건 더 살펴보기',exact:true}).click();await expect(cards).toHaveCount(31);
 await page.getByRole('navigation',{name:'뉴스 분류'}).getByRole('link',{name:/자격증/}).click();await expect(cards).toHaveCount(0);await expect(dock).toContainText('1개의 뉴스를 골랐어요');
 await page.getByRole('navigation',{name:'뉴스 분류'}).getByRole('link',{name:/AI·자동화/}).click();await expect(cards).toHaveCount(9);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(writes).toEqual([]);
});

test('공식 뉴스와 플랫폼 소식은 한 눈에 구분되고 트렌드 조사와 출처 관리는 같은 화면에 있다',async({page})=>{
  const writes = await researchHarness(page);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/news');
  const navigation = page.getByRole('navigation', { name: '소식 보기' });
  const settings = page.getByText('소재 참고 조사 · 설정과 결과', { exact: true });
  await expect(settings).not.toBeVisible();
  await expect(navigation.getByRole('link')).toHaveCount(2);
  await navigation.getByRole('link', { name: '플랫폼 소식', exact: true }).click();
  await expect(settings).toBeVisible();
  await expect(page.getByRole('combobox', { name: '출처 플랫폼', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '뉴스 선택과 작업 만들기' })).not.toBeVisible();
  const youtube = page.getByRole('region', { name: 'YouTube 공개 후보' });
  await expect(youtube.getByText('누적 조회수 순', { exact: true })).toBeVisible();
  await expect(youtube.getByText(/최근 7일 발행 · 최근 7일 지표 확인/)).toBeVisible();
  await expect(youtube.getByText('YouTube Data API · 한국·주제 검색 표본')).toBeVisible();
  const references = youtube.getByText('참고 게시물 1건', { exact: true });
  await expect(youtube.getByRole('link', { name: '발행일 미확인 영상' })).not.toBeVisible();
  await references.click();
  await expect(youtube.getByRole('link', { name: '발행일 미확인 영상' })).toBeVisible();
  await expect(youtube.getByText('발행일을 확인하지 못했습니다.')).toBeVisible();
  await expect(page.getByText('누적 조회수 1,250')).toBeVisible();
  const filter = page.getByRole('combobox', { name: '출처 플랫폼', exact: true });
  await filter.selectOption('instagram');
  await expect(page.getByRole('link', { name: '인스타 공개 후보' })).toBeVisible();
  await expect(page.getByRole('link', { name: '정기 검색 영상' })).toHaveCount(0);
  await expect(page.getByText('좋아요 0')).toBeVisible();
  await expect(page.getByText('댓글 약 50')).toBeVisible();
  await expect(page.getByText(/누적 조회수/)).toHaveCount(0);
  await filter.selectOption('naver_blog');
  const naver = page.getByRole('region', { name: '네이버 블로그 공개 후보' });
  await expect(naver.getByText('최신 발행일 순', { exact: true })).toBeVisible();
  await expect(naver.getByText('공개 RSS · 등록 블로그 표본')).toBeVisible();
  await filter.selectOption('linkedin');
  await expect(page.getByText('수집 대기', { exact: true })).toBeVisible();
  await settings.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: '게시할 콘텐츠의 소재 참고 조사' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(writes).toEqual([]);
});

test('게시 대상 저장은 조사만 요청하고 시간·원고·승인을 쓰지 않는다',async({page})=>{
  const writes=await researchHarness(page);
  await page.setViewportSize({width:390,height:844});await page.goto('/news?tab=platforms');
  await page.getByText('소재 참고 조사 · 설정과 결과', { exact: true }).click();
  const panel=page.getByRole('region',{name:'게시할 콘텐츠의 소재 참고 조사'});
  await panel.getByRole('checkbox',{name:'LinkedIn',exact:true}).check();
  await panel.getByLabel('조사 주제',{exact:true}).fill('AI agent');
  const topic=panel.getByLabel('조사 주제',{exact:true});
  expect(await topic.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  expect((await topic.boundingBox())!.width).toBeGreaterThan(200);
  await panel.getByRole('button',{name:'조건 저장하고 조사 요청'}).click();
  await expect(panel.getByText(/설정과 조사 요청을 저장했습니다/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({path:'/api/discovery',csrf:'contract-token',body:{platforms:['youtube','tistory','linkedin'],topic:'AI agent',expected_hash:'a'.repeat(64)}});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('출처 실패와 누적 반응을 구분하고 조회만으로 업무를 쓰지 않는다',async({page})=>{
  const writes=await researchHarness(page,[],true);await page.goto('/news?tab=platforms');
  await page.getByText('소재 참고 조사 · 설정과 결과', { exact: true }).click();
  const panel=page.getByRole('region',{name:'게시할 콘텐츠의 소재 참고 조사'});
  await panel.getByText('참고 출처와 수집 상태 (2개)',{exact:true}).click();
  await expect(panel.getByText('HN · 수집 실패',{exact:true})).toBeVisible();
  const oldResults = panel.getByText('이전 조건의 소재 후보 보기', { exact: true });
  const youtube = panel.getByText('YouTube·Shorts 소재 후보 1건', { exact: true });
  await expect(youtube).not.toBeVisible();
  await oldResults.click();
  await youtube.click();
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
  else if(path==='/api/source-library')body={areas:[],items:[],stats:{items:0,ready:0,passages:0,evidence:0,needs_check:0},vectors:{passages:0,ready:0,pending:0,available:false},limits:{links:10,file_mb:8,memo_chars:60000}};
  else if(path==='/api/newsletters')body={issues:[]};
  else if(path.endsWith('/deliveries'))body={deliveries:[],youtube_configured:false};
  await route.fulfill({status:body===undefined?404:200,contentType:'application/json',body:JSON.stringify(body??{detail:'Synthetic fixture endpoint intentionally unavailable'})});
 });
 return {writes,old};
}

test('뉴스 작업 재열기는 해당 ID로 이동하고 오래된 작업도 목록 맨 위에 표시한다',async({page})=>{
 const {writes,old}=await newsJobHarness(page);await page.goto('/news?seg=all');
 await page.getByRole('checkbox',{name:'선택한 뉴스 선택',exact:true}).check();
 // 2026-11-02 operator instruction (one click from news to draft): with auto drafting on and the window closed,
 // the button itself states that it opens a 120-minute window, so the click is the explicit confirmation.
 await page.getByRole('button',{name:'작업 시간 120분 열고 작업 만들기',exact:true}).click();
 await expect(page).toHaveURL(`/scripts/${old.id}`);
 await expect(page.locator('.job-list .job-item').first()).toHaveAttribute('aria-current','page');
 await expect(page.locator('.job-list .job-item').first()).toContainText(old.title);
 await expect(page.getByRole('button',{name:'원고 생성 시작',exact:true})).toBeEnabled();
 expect(writes).toEqual([{path:'/api/session/window',body:{minutes:120}},{path:'/api/jobs',body:{article_ids:['news-one'],start_draft:true}}]);
});

test('닫힌 작업 시간은 실행 확인 후에만 열고 원고를 요청하며 승인·제작을 자동 실행하지 않는다',async({page})=>{
 const {writes,old}=await newsJobHarness(page);await page.goto(`/scripts/${old.id}`);
 await page.getByRole('button',{name:'원고 생성 시작',exact:true}).click();
 const confirm=page.getByRole('region',{name:'원고 자동 생성 실행 확인'});await expect(confirm).toBeVisible();
 expect(writes).toEqual([]);
 await confirm.getByRole('button',{name:'작업 시간 열고 원고 생성',exact:true}).click();
 await expect.poll(()=>writes.map(row=>row.path)).toEqual(['/api/session/window',`/api/jobs/${old.id}/draft`]);
 // Same 120-minute default as the settings page (draft + review + production exceed 30 minutes).
 expect(writes[0].body).toEqual({minutes:120});
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

for(const width of [1440,375])test(`만들기 ${width}px 원고 승인은 제작 종류만 보내고 채널 정책을 바꾸지 않는다`,async({page})=>{
 const {writes,old}=await newsJobHarness(page,true);await page.setViewportSize({width,height:1000});
 await page.goto(`/scripts/${old.id}`);
 await expect(page.getByRole('heading',{name:'무엇을 만들까요?',exact:true})).toBeVisible();
 await expect(page.getByRole('group',{name:'영상 플랫폼 선택'})).toHaveCount(0);
 await page.getByRole('button',{name:'원고 승인',exact:true}).click();
 const panel=page.getByRole('region',{name:'원고 승인 최종 확인'});
 await expect(panel.getByRole('checkbox')).toHaveCount(0);
 await expect(panel).toContainText('채널 전달');expect(writes).toEqual([]);
 await panel.getByRole('button',{name:'이 원고 승인·자동 제작',exact:true}).click();
 await panel.getByRole('button',{name:'유료 포함 제작 확인',exact:true}).click();
 await expect.poll(()=>writes.length).toBe(1);
 expect(writes[0].body.selections).toEqual(old.selections);
 expect('draft_targets' in writes[0].body).toBe(false);
 expect(writes[0].path).toBe(`/api/jobs/${old.id}/reviews/source`);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
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
 await panel.getByRole('checkbox',{name:/내가 작성했거나 제작에 사용할 권한/}).check();
 await expect(panel.getByRole('checkbox',{name:/내 경험 중심/})).not.toBeChecked();
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
 await expect(outline.getByRole('combobox',{name:'목차 바로 이동'}).locator('option')).toContainText(['흩어진 질문과 소식이 나만의 콘텐츠가 되는 곳.']);
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


for(const width of [375,1440]) test(`파이프라인 ${width}px 바로가기는 제목을 화면에 표시하고 초점을 옮긴다`,async({page})=>{
 const writes=await researchHarness(page);
 const doc=JSON.parse(readFileSync(new URL('../../../backend/config/architecture.json',import.meta.url),'utf8'));
 await page.route('**/api/architecture',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({doc,git:{commit:null,committed_at:null,subject:null,recent:[]},build:null,build_matches_running_code:false,keys:{openai:false,gemini:false,runway:false,youtube:false},profiles:{text:'synthetic',image:'none'},window:{status:'closed'},worker:{state:'stopped'},budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},usage:[]})}));
 await page.setViewportSize({width,height:812});await page.goto('/pipeline');
 await page.getByRole('tab',{name:'운영 상세',exact:true}).click();
 await page.getByRole('link',{name:'서버·연결 경계',exact:true}).press('Enter');
 await expect(page.locator('#pipeline-runtime-title')).toBeInViewport();
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
 const reviewLink=page.getByRole('link',{name:'현재 원고 검토·승인①으로 이동',exact:true});
 await reviewLink.scrollIntoViewIfNeeded();
 expect(await reviewLink.evaluate(el=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('a')===el;})).toBe(true);
 if(width===375)await reviewLink.click();else await reviewLink.press('Enter');
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

for(const width of [1440,375])test(`fragment 새로고침 뒤 ${width}px 왕복에서 URL을 중복하지 않는다`,async({page})=>{
 const {writes,old}=await newsJobHarness(page,true);
 const source=`/scripts/${old.id}#studio-blog-${old.id}`;
 await page.setViewportSize({width,height:900});await page.goto(source);
 await expect(page.locator(`#studio-blog-${old.id}`)).toBeVisible();
 await page.reload();
 const body=page.getByRole('textbox',{name:'본문 · Markdown',exact:true});
 const expected=(await body.inputValue())+' 보존할 임시 메모';await body.fill(expected);
 const docs:string[]=[];page.on('request',r=>{if(r.isNavigationRequest())docs.push(r.url());});
 for(let round=0;round<2;round++){
  await page.getByRole('button',{name:'완성 영상 확인',exact:true}).click();
  await expect(page).toHaveURL(`/publish?job=${old.id}`);
  const link=page.getByRole('link',{name:'현재 원고 검토·승인①으로 이동',exact:true});
  if(width===375)await link.click();else await link.press('Enter');
  await expect(page).toHaveURL(source);
  await expect(page.locator(`#studio-blog-${old.id}`)).toBeFocused();
  await expect(body).toHaveValue(expected);
 }
 await page.goBack();await expect(page).toHaveURL(`/publish?job=${old.id}`);
 await page.goForward();await expect(page).toHaveURL(source);
 await expect(body).toHaveValue(expected);
 expect(docs).toEqual([]);expect(writes).toEqual([]);
});

for(const width of [375,768,1280,1440,1920])test(`긴 제작비 안내 ${width}px에서도 승인 설명이 눌리거나 버튼이 넘치지 않는다`,async({page})=>{
 const {old,writes}=await newsJobHarness(page,true);
 Object.assign(old,{state:'release_review',manifest:{hash:'layout-only',files:[{id:'layout-text',name:'tistory.md',kind:'markdown',url:'/api/layout-text',outputs:['blog']}],completed_outputs:['blog','video']}});
 await page.route(`**/api/jobs/${old.id}/production-estimate*`,route=>route.fulfill({contentType:'application/json',body:JSON.stringify({clips:{paid:true,clips:5,credits:200,reservation_krw:4000,daily_cap:15,used_today:5,label:'유료: 영상 클립 5개(장면 길이에 맞춤) · 최대 200크레딧($2.00, 예약 최대 4,000원)'},thumbnail_artwork:true})}));
 await page.setViewportSize({width,height:1000});await page.goto(`/scripts/${old.id}`,{waitUntil:'domcontentloaded'});
 const panel=page.locator('.approval-panel');await expect(panel.getByText(/오늘 5\/15개 사용/)).toBeVisible();
 await expect(panel).not.toContainText('현재 버전을 승인하세요');
 await expect(panel).toContainText('완성본은 제작·출고함에서 확인하세요.');
 const check=async()=>{
  const box=await panel.boundingBox();const copy=await panel.locator(':scope > div').first().boundingBox();
  expect(copy!.width).toBeGreaterThanOrEqual(Math.min(240,box!.width));expect(copy!.height).toBeLessThan(250);
  for(const e of await panel.locator('.approval-actions, .produce-confirm, .paid-notice, button').all()){
   const b=await e.boundingBox();if(b){expect(b.x).toBeGreaterThanOrEqual(box!.x-1);expect(b.x+b.width).toBeLessThanOrEqual(box!.x+box!.width+1);}
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 };
 await check();await panel.getByRole('button',{name:'현재 설정으로 다시 제작',exact:true}).click();
 await expect(panel.getByRole('button',{name:'유료 포함 제작 확인',exact:true})).toBeVisible();await check();
 await panel.getByRole('button',{name:'취소',exact:true}).click();expect(writes).toEqual([]);
 Object.assign(old,{state:'source_approved'});await page.reload({waitUntil:'domcontentloaded'});
 await expect(panel).toContainText('원고 승인이 끝났습니다.');await expect(panel).not.toContainText('현재 버전을 승인하세요');
 Object.assign(old,{state:'release_review'});
 // The same shared approval layout also appears on the delivery page.
 await page.goto(`/publish?job=${old.id}`,{waitUntil:'domcontentloaded'});await expect(page.locator('.approval-panel')).toContainText('완성본을 확인하고 승인하세요');
 const release=page.locator('.approval-panel');const rb=await release.boundingBox();
 for(const e of await release.locator(':scope > div').all()){const b=await e.boundingBox();expect(b!.x+b!.width).toBeLessThanOrEqual(rb!.x+rb!.width+1);}
 expect(writes).toEqual([]);
});

for(const width of [375,1440])test(`승인 최종확인 ${width}px에서도 긴 비용안내와 취소가 영역 안에 남는다`,async({page})=>{
 const {old,writes}=await newsJobHarness(page,true);
 await page.route(`**/api/jobs/${old.id}/production-estimate*`,route=>route.fulfill({contentType:'application/json',body:JSON.stringify({clips:{paid:true,clips:5,credits:200,reservation_krw:4000,daily_cap:15,used_today:5,label:'유료: 영상 클립 5개(장면 길이에 맞춤) · 최대 200크레딧($2.00, 예약 최대 4,000원)'},thumbnail_artwork:true})}));
 await page.setViewportSize({width,height:1000});await page.goto(`/scripts/${old.id}`,{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'원고 승인',exact:true}).click();
 const confirm=page.getByRole('region',{name:'원고 승인 최종 확인'});await expect(confirm.getByText(/오늘 5\/15개 사용/)).toBeVisible();
 await confirm.getByRole('button',{name:'이 원고 승인·자동 제작',exact:true}).click();
 await expect(confirm.getByRole('button',{name:'유료 포함 제작 확인',exact:true})).toBeVisible();
 const box=await confirm.boundingBox();for(const el of await confirm.locator('.produce-confirm, .paid-notice, button').all()){const b=await el.boundingBox();expect(b!.x).toBeGreaterThanOrEqual(box!.x-1);expect(b!.x+b!.width).toBeLessThanOrEqual(box!.x+box!.width+1);}
 await confirm.getByRole('button',{name:'취소',exact:true}).click();await confirm.getByRole('button',{name:'돌아가기',exact:true}).click();
 expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('공개 원문 문단 검색과 사용자 선택을 새 기획 판본에 연결한다', async ({ page }) => {
  const { writes, old } = await newsJobHarness(page);
  const first = { id: 'a'.repeat(64), title: '원문 A', url: 'https://example.org/evidence-a', paragraph: 4, quote: '승인할 첫 번째 원문 문단입니다.', source_sha256: 'b'.repeat(64), quote_sha256: 'c'.repeat(64) };
  const second = { ...first, id: 'd'.repeat(64), title: '원문 B', url: 'https://example.edu/evidence-b', paragraph: 9, quote: '확인할 두 번째 원문 문단입니다.' };
  const initial = 'e'.repeat(64);
  const afterFirst = 'f'.repeat(64);
  const afterSecond = '1'.repeat(64);
  const failedReads: string[] = [];
  page.on('response', (response) => {
    if (response.status() >= 400 && response.request().method() === 'GET') failedReads.push(new URL(response.url()).pathname);
  });
  let idea = { id: 'public-sample', title: '공개 원문 검증 기획', source_url: 'https://example.org/primary', state: 'candidate', blocked: [], reasons: [], score: 60, outlier_band: 'normal', edit_hash: initial, public_evidence: undefined as (typeof first)[] | undefined };
  await page.route('**/api/briefs', route => route.fulfill({ json: { default: '', presets: [] } }));
  await page.route('**/api/questions', route => route.fulfill({ json: { questions: [], groups: [] } }));
  await page.route('**/api/jobs/job-recent', route => route.fulfill({ json: { ...old, id: 'job-recent' } }));
  await page.route('**/api/ideas', route => route.fulfill({ json: { ideas: [idea] } }));
  await page.route('**/api/ideas/public-sample/public-evidence', async route => {
    writes.push({ path: '/api/ideas/public-sample/public-evidence', body: route.request().postDataJSON() });
    idea = { ...idea, edit_hash: idea.edit_hash === initial ? afterFirst : afterSecond, public_evidence: [first, second] };
    await route.fulfill({ json: idea });
  });
  await page.route('**/api/ideas/public-sample/select', async route => {
    writes.push({ path: '/api/ideas/public-sample/select', body: route.request().postDataJSON() });
    idea = { ...idea, state: 'selected' };
    await route.fulfill({ json: { idea, job: old } });
  });

  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/plans');
  const panel = page.getByRole('region', { name: '공개 원문 검증 기획 공개 원문 근거' });
  await panel.getByRole('button', { name: '공개 원문 근거 찾기', exact: true }).click();
  await expect(panel.getByText(first.quote, { exact: true })).toBeVisible();
  await expect(panel.getByText(second.quote, { exact: true })).toBeVisible();
  await expect(panel.getByRole('link', { name: '원문 B 원문 열기' })).toHaveAttribute('href', second.url);
  const firstChoice = panel.getByRole('checkbox', { name: '원문 A · 문단 4' });
  const secondChoice = panel.getByRole('checkbox', { name: '원문 B · 문단 9' });
  await expect(firstChoice).not.toBeChecked();
  await expect(secondChoice).not.toBeChecked();
  await firstChoice.check();
  await panel.getByRole('button', { name: '공개 원문 근거 다시 찾기', exact: true }).click();
  await expect(firstChoice).toBeChecked();
  await expect(secondChoice).not.toBeChecked();
  await firstChoice.uncheck();
  await secondChoice.check();
  expect(writes).toEqual([
    { path: '/api/ideas/public-sample/public-evidence', body: { expected_hash: initial } },
    { path: '/api/ideas/public-sample/public-evidence', body: { expected_hash: afterFirst } },
  ]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(failedReads).toEqual([]);
  await page.getByRole('button', { name: '이 기획으로 작업 만들기', exact: true }).click();
  await expect.poll(() => writes.length).toBe(3);
  expect(writes[2]).toEqual({ path: '/api/ideas/public-sample/select', body: { expected_hash: afterSecond, public_evidence_ids: [second.id] } });
});

const earlierIdeaHash = 'e'.repeat(64);
const updatedIdeaHash = 'f'.repeat(64);
const checkedReferenceId = 'd'.repeat(64);

async function evidenceReviewHarness(page: Page, selected: boolean) {
  const writes: { path: string; body: unknown }[] = [];
  const retained = { id: checkedReferenceId, url: 'https://example.org/source', title: '공식 문서', paragraph: 2, quote: '확인한 원문입니다.' };
  const removed = { ...retained, id: 'b'.repeat(64), paragraph: 3, quote: '현재 문서에서 제외된 문단입니다.' };
  const job = { id: 'job-existing-evidence' };
  let idea = {
    id: 'idea-evidence-regression', title: '새 출처의 게시물', state: selected ? 'selected' : 'candidate', score: 0, reasons: [],
    source_url: selected ? retained.url : null, edit_hash: earlierIdeaHash, outlier_band: 'unknown',
    blocked: selected ? [] : ['1차 출처 없음'],
    public_evidence_reviewable: selected, public_evidence: selected ? [] : [retained, removed],
    approved_public_evidence_ids: [] as string[],
  };
  await page.route('**/api/**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const ideaPath = '/api/ideas/' + idea.id;
    if (req.method() !== 'GET') writes.push({ path, body: req.postDataJSON() });
    let body: unknown = {};
    if (path === '/api/ideas') body = { ideas: [idea] };
    else if (path === ideaPath + '/sources') {
      idea = { ...idea, source_url: retained.url, blocked: [], edit_hash: updatedIdeaHash, public_evidence: [retained] };
      body = idea;
    } else if (path === ideaPath + '/public-evidence') {
      idea = { ...idea, edit_hash: updatedIdeaHash, public_evidence: [retained] };
      body = idea;
    } else if (path === ideaPath + '/public-evidence/approve') {
      idea = { ...idea, edit_hash: 'a'.repeat(64), approved_public_evidence_ids: [retained.id] };
      body = { idea, job };
    } else if (path === '/api/dashboard') {
      body = {
        articles: [], jobs: [], feeds: [], agents: [], events: [], tasks: [],
        budget: { cap_krw: 10000, spent_krw: 0, reserved_krw: 0, remaining_krw: 10000 },
        window: { status: 'closed', authorized_end: '2026-10-01T00:00:00Z' },
        provider: { model: 'fixture', configured: false }, knowledge: {},
      };
    } else if (path === '/api/questions') body = { questions: [], groups: [] };
    else if (path === '/api/channels') body = { channels: [] };
    else if (path === '/api/briefs') body = { default: '', presets: [] };
    else if (path === '/api/session') body = { csrf: 'contract-token' };
    else if (path === '/api/jobs/summaries') body = { jobs: [] };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('/plans#' + idea.id);
  return { writes, job, idea: page.locator('#' + idea.id) };
}

test('대표 출처 저장이 현재 응답에서 확인된 근거 체크만 유지한다', async ({ page }) => {
  const { writes, idea } = await evidenceReviewHarness(page, false);
  const retained = idea.getByRole('checkbox', { name: '공식 문서 · 문단 2' });
  await retained.check();
  await idea.getByRole('checkbox', { name: '공식 문서 · 문단 3' }).check();
  await idea.getByText('출처 확인·보완', { exact: true }).click();
  await idea.getByRole('textbox', { name: /공개 HTTPS 원출처 주소/ }).fill('https://example.org/source');
  await idea.getByRole('checkbox', { name: /각 주소의 본문과 기획 관련성을 직접 확인했습니다/ }).check();
  await idea.getByRole('button', { name: '확인한 출처 저장' }).click();
  await expect(idea.getByText('막힌 이유: 1차 출처 없음')).toHaveCount(0);
  await expect(idea.getByRole('checkbox', { name: '공식 문서 · 문단 3' })).toHaveCount(0);
  await expect(retained).toBeChecked();
  await expect(idea.getByRole('button', { name: '이 기획으로 작업 만들기' })).toBeEnabled();
  expect(writes).toEqual([{
    path: '/api/ideas/idea-evidence-regression/sources',
    body: { expected_hash: earlierIdeaHash, source_urls: ['https://example.org/source'], operator_verified: true },
  }]);
});

test('선택한 기획에서 근거만 다시 골라 같은 작업에 승인하고 재열람한다', async ({ page }) => {
  const { writes, job, idea } = await evidenceReviewHarness(page, true);
  await expect(idea.getByRole('button', { name: '선택됨' })).toBeDisabled();
  await idea.getByRole('button', { name: /공개 원문 근거.*찾기/ }).click();
  const evidence = idea.getByRole('checkbox', { name: '공식 문서 · 문단 2' });
  await expect(evidence).not.toBeChecked();
  const approve = idea.getByRole('button', { name: '선택한 근거를 승인⓪에 반영' });
  await expect(approve).toBeDisabled();
  await evidence.check();
  await approve.click();
  await expect(idea.getByText('선택한 근거를 기존 작업에 연결했습니다.')).toBeVisible();
  await expect(idea.getByRole('link', { name: '기존 작업 열기' })).toHaveAttribute('href', '/scripts/' + job.id);
  await page.reload();
  await expect(evidence).toBeChecked();
  await evidence.uncheck();
  await expect(approve).toBeDisabled();
  expect(writes).toEqual([
    { path: '/api/ideas/idea-evidence-regression/public-evidence', body: { expected_hash: earlierIdeaHash } },
    { path: '/api/ideas/idea-evidence-regression/public-evidence/approve', body: { expected_hash: updatedIdeaHash, public_evidence_ids: [checkedReferenceId] } },
  ]);
});
