import { test, expect, type Page } from '@playwright/test';

// Synthetic contracts: no source requests, account, approval or production writes.
async function researchHarness(page: Page) {
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
    else if (path==='/api/dashboard') body={articles:[],jobs:[],feeds:[],agents:[],events:[],tasks:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed',authorized_end:'2026-10-01T00:00:00Z'},provider:{model:'gpt-5.4-mini',configured:false},knowledge:{}};
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
