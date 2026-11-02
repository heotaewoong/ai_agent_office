import {test,expect,type Page} from '@playwright/test';

async function harness(page:Page, holdPrepared=false, failSecondPrepare=false) {
  const id='newsletter-contract',hash='a'.repeat(64),review='c'.repeat(64);
  const job={id,title:'검토한 AI 뉴스',state:'release_approved',source_hash:hash,
    article:{id:'one',title:'검토한 AI 뉴스',url:'https://example.org/research'},
    selections:{blog:true,video:false,pdf:false,cards:false},source_packet:{title:'검토한 AI 뉴스',body:'출처를 확인한 합성 시험 원고입니다.',quality:{status:'passed',critical:false}},
    source_approval:{decision:'approved',version:hash},release_approval:{decision:'approved',version:'m'.repeat(64),outputs:['blog']},
    manifest:{hash:'m'.repeat(64),source_hash:hash,files:[],completed_outputs:['blog']},tasks:[],events:[],drafts:[]};
  const dashboard={articles:[],jobs:[job],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'closed'},provider:{model:'synthetic',configured:false},knowledge:{}};
  let issue:any=null,prepared:any=null;const writes:{path:string;body:any}[]=[];
  let releasePrepared:((value:any)=>Promise<void>)|undefined,preparedReads=0,prepareWrites=0;
  const destinations=['email','slack','website'].map((key,i)=>({key,label:['구독자 이메일','Slack','heobrain.kr'][i],configured:false,verified:false,missing:['연결 설정'],note:'실제 연결은 아직 검증하지 않았습니다.'}));
  await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;let response:any;
    if(req.method()!=='GET')writes.push({path,body:req.postDataJSON()});
    if(path===`/api/jobs/${id}/newsletter`){
      const body=req.postDataJSON();issue={id:'issue-contract',job_id:id,state:'draft',subject:body.subject,issue_key:body.issue_key,markdown:'# 검토한 원고',hash:'b'.repeat(64),review_hash:review,recipients_hash:'d'.repeat(64),recipient_count:0,built_at:new Date().toISOString(),editorial:body.editorial,package:{version:1,article_count:2,publisher_count:2,source_note:'발행사 수는 독립 검증 수가 아닙니다.',sources:[{job_id:id,title:job.title,url:'https://example.org/research',publisher:'example.org'}],snapshots:[],outputs:{email:{html:'<!doctype html><html lang="ko"><body><h1>검토한 이메일 원고</h1></body></html>',text:'검토한 이메일 원고'},slack:{text:'Slack용 검토한 뉴스 요약'},website:{title:'웹사이트 초안',markdown:'검토한 웹사이트 원고',state:'draft'}}}};response=issue;
    } else if(path.endsWith('/review')){issue={...issue,state:'approved',approval:{stage:'③',decision:'approved',actor:'synthetic',at:new Date().toISOString(),note:''}};response=issue;}
    else if(path.endsWith('/prepare')){
      if(failSecondPrepare&&prepareWrites++>0){await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'목적지 설정이 변경되었습니다'})});return;}
      prepared={id:'prepared-one',issue_id:issue.id,review_hash:review,state:'connection_required',external_requests:0,destinations:destinations.map(row=>({...row,external_sent:false})),note:'발송·게시하지 않았습니다.'};response=prepared;
    }
    else if(path.endsWith('/prepared')){
      if(holdPrepared&&preparedReads++===0){releasePrepared=value=>route.fulfill({contentType:'application/json',body:JSON.stringify({prepared:value})});return;}
      response={prepared};
    }
    else if(path==='/api/newsletters')response={issues:issue?[issue]:[]};
    else if(path==='/api/newsletter-connections')response={mode:'prepare-only',destinations};
    else if(path==='/api/newsletter-inputs')response={sources:[{id:'one',name:'연구기관 A',segment:'ai',language:'en'},{id:'two',name:'공식 발표 B',segment:'ai',language:'en'}],released_jobs:[{id,title:job.title},{id:'job-second',title:'다른 기관의 출고 원고'}]};
    else if(path==='/api/dashboard')response=dashboard;
    else if(path==='/api/jobs/summaries')response={jobs:[job]};
    else if(path===`/api/jobs/${id}`)response=job;
    else if(path==='/api/session')response={csrf:'synthetic-token'};
    else if(path==='/api/channels')response={channels:[]};
    else if(path.endsWith('/deliveries'))response={deliveries:[],youtube_configured:false};
    else if(path.endsWith('/production-estimate'))response={clips:{paid:false},thumbnail_artwork:false};
    await route.fulfill({status:response===undefined?404:200,contentType:'application/json',body:JSON.stringify(response??{detail:'합성 시험에서 사용하지 않는 경로'})});
  });
  return {writes,hasPending:()=>!!releasePrepared,releasePrepared:async(value:any)=>{if(!releasePrepared)throw new Error('준비 조회가 시작되지 않았습니다');await releasePrepared(value);}};
}

for(const width of [1440,375])test(`뉴스레터 ${width}px 여러 원고·3목적지·③·전달 준비까지만`,async({page})=>{
  const pageErrors:string[]=[];
  page.on('pageerror',error=>pageErrors.push(error.message));
  page.on('requestfailed',request=>console.error('검수 요청 실패:',new URL(request.url()).pathname,request.failure()?.errorText));
  const {writes}=await harness(page);await page.setViewportSize({width,height:1000});await page.goto('/publish?job=newsletter-contract');
  await page.getByText('뉴스레터 회차 · 별도 승인③',{exact:true}).click();
  const panel=page.getByRole('region',{name:'뉴스레터 회차',exact:true});
  await panel.getByRole('combobox',{name:'회차 목적',exact:true}).selectOption('analysis');
  await panel.getByLabel('함께 실을 원고 · 다른 기관의 출고 원고',{exact:true}).check();
  await expect(panel.getByRole('checkbox',{name:'전달 목적지 · 구독자 이메일',exact:true})).toBeChecked();
  await panel.getByRole('button',{name:'이 작업으로 회차 만들기',exact:true}).click();
  await expect(panel.getByTitle('이메일 미리보기')).toBeVisible();
  await expect(panel.getByTitle('이메일 미리보기')).toHaveAttribute('sandbox','');
  if(process.env.NEWSLETTER_UI_EVIDENCE_DIR)await panel.screenshot({path:`${process.env.NEWSLETTER_UI_EVIDENCE_DIR}/2026-11-02_뉴스레터_후보_${width}_미리보기_PRIVATE.png`});
  const prepare=panel.getByRole('button',{name:'선택한 목적지 전달 준비',exact:true});await expect(prepare).toBeDisabled();
  await panel.getByRole('button',{name:'Slack 원문',exact:true}).click();await expect(panel.getByText('Slack용 검토한 뉴스 요약',{exact:true})).toBeVisible();
  await panel.getByRole('button',{name:'웹사이트 초안',exact:true}).click();await expect(panel.getByText('검토한 웹사이트 원고',{exact:true})).toBeVisible();
  await panel.getByRole('button',{name:'③ 회차 승인',exact:true}).click();await expect(prepare).toBeEnabled();
  await prepare.click();await expect(panel.getByText('전달 준비 기록 · 연결 설정 필요',{exact:true})).toBeVisible();
  const build=writes.find(row=>row.path.endsWith('/newsletter'))!;
  expect(build.body.editorial).toEqual({kind:'analysis',related_job_ids:['job-second'],destinations:['email','slack','website']});
  expect(writes.filter(row=>row.path.endsWith('/prepare'))).toHaveLength(1);
  expect(writes.find(row=>row.path.endsWith('/prepare'))!.body).toEqual({expected_hash:'c'.repeat(64)});
  expect(writes.every(row=>!row.path.includes('/send')&&!row.path.includes('/publish'))).toBe(true);
  const geometry=await panel.evaluate(el=>({width:el.getBoundingClientRect().width,children:[...el.querySelectorAll('fieldset,iframe,pre')].map(child=>child.getBoundingClientRect().width),doc:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
  expect(geometry.doc).toBeLessThanOrEqual(geometry.client);expect(geometry.children.every(w=>w<=geometry.width)).toBe(true);
  expect(pageErrors).toEqual([]);
  if(process.env.NEWSLETTER_UI_EVIDENCE_DIR)await panel.screenshot({path:`${process.env.NEWSLETTER_UI_EVIDENCE_DIR}/2026-11-02_뉴스레터_후보_${width}_준비상태_PRIVATE.png`});
});

test('늦은 초기 준비 조회가 방금 완료한 준비 결과를 지우지 않는다',async({page})=>{
  const fixture=await harness(page,true);await page.goto('/publish?job=newsletter-contract');
  await page.getByText('뉴스레터 회차 · 별도 승인③',{exact:true}).click();
  const panel=page.getByRole('region',{name:'뉴스레터 회차',exact:true});
  await expect(panel.getByRole('button',{name:'이 작업으로 회차 만들기',exact:true})).toBeEnabled();
  await panel.getByRole('button',{name:'이 작업으로 회차 만들기',exact:true}).click();
  await expect.poll(fixture.hasPending).toBe(true);
  await panel.getByRole('button',{name:'③ 회차 승인',exact:true}).click();
  await panel.getByRole('button',{name:'선택한 목적지 전달 준비',exact:true}).click();
  await expect(panel.getByText('전달 준비 기록 · 연결 설정 필요',{exact:true})).toBeVisible();
  const response=page.waitForResponse(value=>new URL(value.url()).pathname.endsWith('/prepared'));
  await fixture.releasePrepared(null);await response;
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await expect(panel.getByText('전달 준비 기록 · 연결 설정 필요',{exact:true})).toBeVisible();
  expect(fixture.writes.filter(row=>row.path.endsWith('/prepare'))).toHaveLength(1);
});

test('변경된 목적지로 준비가 거절되면 이전 준비 기록 표시를 지운다',async({page})=>{
  await harness(page,false,true);await page.goto('/publish?job=newsletter-contract');
  await page.getByText('뉴스레터 회차 · 별도 승인③',{exact:true}).click();
  const panel=page.getByRole('region',{name:'뉴스레터 회차',exact:true});
  await expect(panel.getByRole('button',{name:'이 작업으로 회차 만들기',exact:true})).toBeEnabled();
  await panel.getByRole('button',{name:'이 작업으로 회차 만들기',exact:true}).click();
  await panel.getByRole('button',{name:'③ 회차 승인',exact:true}).click();
  const button=panel.getByRole('button',{name:'선택한 목적지 전달 준비',exact:true});
  await button.click();await expect(panel.getByText('전달 준비 기록 · 연결 설정 필요',{exact:true})).toBeVisible();
  await expect(button).toBeEnabled();await button.click();
  await expect(page.getByRole('alert',{name:'작업 처리 상태'})).toContainText('목적지 설정이 변경되었습니다');
  await expect(panel.getByText('전달 준비 기록 · 연결 설정 필요',{exact:true})).toHaveCount(0);
});
