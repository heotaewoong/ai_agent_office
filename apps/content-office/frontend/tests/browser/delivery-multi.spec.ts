import {test,expect,type Page} from '@playwright/test';

async function harness(page:Page,closed=false){
 const hash='a'.repeat(64),source='b'.repeat(64),id='multi-delivery-test';
 const channels=[['youtube_main_ko','youtube','YouTube 메인'],['instagram_main','instagram','Instagram 메인'],['linkedin_personal','linkedin','LinkedIn 개인'],['tistory_main','tistory','티스토리']].map(([key,platform,label])=>({key,platform,label,locale:'ko',public_url:'https://example.com/'+key,external_account_id:key,publication_enabled:true,credentials_configured:true,delivery:'manual'}));
 const job:any={id,title:'멀티 전달 검증 원고',state:'release_approved',updated_at:'2026-11-02T00:00:00Z',article:{id:'one',title:'합성 원고',url:'https://example.com'},selections:{blog:true,video:true,cards:false,pdf:false},source_hash:source,source_packet:{title:'멀티 전달 검증 원고',body:'합성 UI 계약입니다.',audience:{language:'ko'},evidence:[],video:{scenes:[]},quality:{status:'passed',critical:false}},source_approval:{decision:'approved',version:source},manifest:{hash,source_hash:source,thumbnail_candidates:[],files:['linkedin-personal.txt','tistory.md'].map((name,i)=>({id:'f'+i,name,kind:'text',outputs:['blog'],sha256:hash,url:'/api/test/'+name}))},release_approval:{decision:'approved',version:hash,outputs:['video','blog']},tasks:[],events:[],drafts:[]};
 const staging={job_id:id,source_hash:source,manifest_hash:hash,current_release:true,recorded_current:false,stage_hash:hash,blockers:[],notes:[],channels:channels.map(c=>({channel_key:c.key,label:c.label,platform:c.platform,locale:c.locale,local_ready:true,blockers:[],required_files:[],files:[],external_state:'not_attempted',external_id:null,external_draft_created:false}))};
 const writes:any[]=[];let items:any[]=[];
 await page.route('**/api/**',async route=>{const req=route.request(),path=new URL(req.url()).pathname;let body:any;
  if(req.method()!=='GET')writes.push({path,body:req.postDataJSON()});
  if(path==='/api/session')body={csrf:'synthetic-multi'};
  else if(path==='/api/dashboard')body={articles:[],jobs:[job],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:closed?'closed':'active',authorized_end:new Date(Date.now()+(closed?-3600000:3600000)).toISOString()},provider:{configured:false},knowledge:{}};
  else if(path==='/api/jobs/summaries')body={jobs:[job]};else if(path==='/api/jobs/'+id)body=job;
  else if(path==='/api/channels')body={channels};else if(path.endsWith('/staging'))body=staging;
  else if(path.endsWith('/owner-drafts/request')){items.push({id:'draft-'+req.postDataJSON().channel_key,channel_key:req.postDataJSON().channel_key,state:'pending'});body={items};}
  else if(path.endsWith('/reviews/release')){job.release_approval={decision:'approved',version:job.manifest.hash,outputs:req.postDataJSON().outputs};job.state='release_approved';body=job;}
  else if(path.endsWith('/owner-drafts'))body={items};else if(path.endsWith('/deliveries'))body={deliveries:[],youtube_configured:true};
  else if(path.endsWith('/production-estimate'))body={clips:{paid:false},thumbnail_artwork:false};
  await route.fulfill({status:body===undefined?404:200,contentType:'application/json',body:JSON.stringify(body??{detail:'Synthetic endpoint not implemented'})});
 });return {id,writes,job};
}

for(const width of [1440,375])test(`복수 대상 ${width}px 영상·글·미연결 상태를 함께 비교하고 개별 요청한다`,async({page})=>{
 const f=await harness(page);await page.setViewportSize({width,height:1000});await page.goto('/publish?job='+f.id);
 const panel=page.getByRole('region',{name:'멀티플랫폼 전달 선택',exact:true});
 for(const name of ['YouTube 메인 · 한국어','Instagram 메인 · 한국어','LinkedIn 개인 · 한국어','티스토리 · 한국어'])await panel.getByRole('checkbox',{name,exact:true}).check();
 await expect(panel.getByRole('checkbox',{checked:true})).toHaveCount(4);expect(f.writes).toEqual([]);
 const yt=panel.getByRole('region',{name:'YouTube 메인 전달 준비'}),ig=panel.getByRole('region',{name:'Instagram 메인 전달 준비'}),li=panel.getByRole('region',{name:'LinkedIn 개인 전달 준비'});
 await expect(yt).toContainText('영상 · YouTube 비공개');await expect(ig).toContainText('외부 임시저장은 미연결');await expect(ig.getByRole('button')).toHaveCount(0);
 await expect(li).toContainText('영상·카드 첨부 전송은 아직 연결되지 않았습니다');
 page.once('dialog',d=>d.dismiss());await li.getByRole('button',{name:'LinkedIn 개인에 원고 임시저장 요청'}).click();expect(f.writes).toEqual([]);
 page.once('dialog',d=>d.accept());await li.getByRole('button',{name:'LinkedIn 개인에 원고 임시저장 요청'}).click();
 await expect(li.getByRole('button',{name:'기존 전달 기록 확인 · 재전송 안 함'})).toBeDisabled();
 expect(f.writes).toEqual([{path:`/api/jobs/${f.id}/owner-drafts/request`,body:{version:f.job.manifest.hash,channel_key:'linkedin_personal',target:{key:'linkedin_personal',platform:'linkedin',locale:'ko',public_url:'https://example.com/linkedin_personal',external_account_id:'linkedin_personal',publication_enabled:true}}}]);
 await expect(panel.getByRole('checkbox',{checked:true})).toHaveCount(4);
 expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('종료된 작업 시간에는 선택과 비교만 허용하고 전송을 막는다',async({page})=>{
 const f=await harness(page,true);await page.goto('/publish?job='+f.id);const panel=page.getByRole('region',{name:'멀티플랫폼 전달 선택'});
 await panel.getByRole('checkbox',{name:'티스토리 · 한국어',exact:true}).check();await expect(panel.getByRole('button',{name:'티스토리에 원고 임시저장 요청'})).toBeDisabled();expect(f.writes).toEqual([]);
});

for(const width of [1440,375])test(`완성본 승인 ${width}px 요약·부분 승인만 처리하고 전송을 섞지 않는다`,async({page})=>{
 const f=await harness(page);f.job.state='partial_release_review';f.job.release_approval=null;
 f.job.manifest.completed_outputs=['blog'];f.job.manifest.output_status={blog:{state:'completed'},video:{state:'failed',error:'합성 실패; 기존 파일 보존'}};
 await page.setViewportSize({width,height:1000});await page.goto('/publish?job='+f.id);
 const scope=page.getByRole('region',{name:'제작물 승인 범위'});
 await expect(scope).toContainText('블로그·소셜 검토 초안');await expect(scope).toContainText('제작 실패');
 await expect(scope.getByRole('checkbox')).toHaveCount(0);
 await scope.locator('summary').click();
 await expect(scope.getByRole('checkbox',{name:'세로 영상 출고',exact:true})).toBeDisabled();
 await expect(scope.getByRole('checkbox',{name:'블로그·소셜 검토 초안 출고',exact:true})).toBeChecked();
 await page.getByRole('button',{name:'출고 승인',exact:true}).click();
 const confirm=page.getByRole('region',{name:'출고 승인 확인'});
 await expect(confirm.getByRole('combobox')).toHaveCount(0);await expect(confirm).toContainText('채널 전달');
 expect(f.writes).toEqual([]);await confirm.getByRole('button',{name:'이 파일 버전 승인하기'}).click();
 await expect.poll(()=>f.writes.length).toBe(1);expect(f.writes[0]).toEqual({path:`/api/jobs/${f.id}/reviews/release`,body:{version:f.job.manifest.hash,decision:'approved',media_reviewed:false,outputs:['blog']}});
 expect(f.job.selections).toEqual({blog:true,video:true,cards:false,pdf:false});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('이전 Reels 전용 판본은 기존 목적지 수정·재승인 경로를 채널 전달에서 제공한다',async({page})=>{
 const f=await harness(page);f.job.source_packet.video_platforms=['instagram_reels'];await page.goto('/publish?job='+f.id);
 const panel=page.getByRole('region',{name:'멀티플랫폼 전달 선택'});
 await panel.getByRole('checkbox',{name:'YouTube 메인 · 한국어',exact:true}).check();
 await expect(panel.getByRole('button',{name:'비공개로 올리기'})).toBeDisabled();
 await panel.locator('summary').filter({hasText:'이전 영상 목적지 수정'}).click();
 await expect(panel.getByRole('group',{name:'영상 플랫폼 선택'})).toBeVisible();
 await expect(panel).toContainText('새 원고 판본에서 승인①·②');
 expect(f.writes).toEqual([]);expect(f.job.source_packet.video_platforms).toEqual(['instagram_reels']);
});
