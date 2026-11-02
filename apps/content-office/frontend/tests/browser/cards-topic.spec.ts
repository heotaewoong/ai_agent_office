import {test,expect} from '@playwright/test';

for(const width of [1440,375])test(`이전 원고 카드 ${width}px는 현재 카드처럼 펼쳐 보이지 않는다`,async({page})=>{
  const id='cards-topic-contract',hash='a'.repeat(64),title='전파망원경에 AI 에이전트를 붙인 이유';
  const job={id,title,state:'source_review',source_hash:hash,source_packet:{title,body:'전파망원경의 관측과 분석을 AI 에이전트로 연결한 연구 소식입니다.',quality:{status:'unverified'}},article:{id:'one',title,url:'https://example.org/research'},selections:{blog:true,video:false,cards:true,pdf:false},tasks:[],events:[],drafts:[]};
  const cards={version:1,source_hash:'old-source',generated_at:'2026-11-02T03:52:00Z',checks:{passed:true,issues:[]},slides:[{index:1,title:'AI 뉴스 봐도 막히나요',body:'내 업무에 적용하는 고민',artifact_id:'old_card'}]};
  const writes:string[]=[];const errors:string[]=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message)});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;if(route.request().method()!=='GET')writes.push(path);
    if(path.startsWith('/api/artifacts/')){await route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080"><rect width="1080" height="1080" fill="#223322"/></svg>'});return;}
    let body:any;
    if(path==='/api/dashboard')body={articles:[],jobs:[job],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed'},provider:{configured:false},knowledge:{}};
    else if(path==='/api/jobs/summaries')body={jobs:[job]};
    else if(path===`/api/jobs/${id}`)body=job;
    else if(path.endsWith('/cards'))body={cards};
    else if(path==='/api/session')body={csrf:'synthetic-token'};
    await route.fulfill({status:body===undefined?404:200,json:body??{detail:'합성 시험에서 사용하지 않는 경로'}});
  });
  await page.setViewportSize({width,height:1000});await page.goto(`/scripts/${id}`);
  const panel=page.locator('section.cards-panel[aria-label="카드뉴스"]');
  await expect(panel.getByText(`현재 원고: ${title}`,{exact:true})).toBeVisible();
  await expect(panel.getByText(/현재 원고로 만든 카드는 아직 없습니다/)).toBeVisible();
  await expect(panel.getByRole('heading',{name:'AI 뉴스 봐도 막히나요',exact:true})).not.toBeVisible();
  const archive=panel.getByText('이전 원고 카드 1장 확인',{exact:true});await archive.click();
  await expect(panel.getByRole('heading',{name:'AI 뉴스 봐도 막히나요',exact:true})).toBeVisible();
  await archive.click();await expect(panel.getByRole('heading',{name:'AI 뉴스 봐도 막히나요',exact:true})).not.toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
  expect(writes).toEqual([]);expect(errors).toEqual([]);
  if(process.env.CARDS_UI_EVIDENCE_DIR)await panel.screenshot({path:`${process.env.CARDS_UI_EVIDENCE_DIR}/2026-11-02_카드뉴스_주제보존_${width}_PRIVATE.png`});
  cards.source_hash=hash;
  await page.reload();
  await expect(panel.getByText('현재 원고 카드 1장',{exact:true})).toBeVisible();
  await expect(panel.getByRole('heading',{name:'AI 뉴스 봐도 막히나요',exact:true})).toBeVisible();
  await expect(panel.getByText(/현재 원고로 만든 카드는 아직 없습니다/)).toHaveCount(0);
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});
