import {test,expect} from '@playwright/test';

for(const width of [1440,375])for(const initial of ['unavailable','stale'])test(`구성 점검 ${width}px ${initial} 복구는 읽기만 하고 판본을 구분한다`,async({page})=>{
 const id='diagnostics-contract',hash='a'.repeat(64),writes:string[]=[],errors:string[]=[];let valid=false;
 const job={id,title:'전파망원경에 AI를 붙인 이유',article:{id:'synthetic',title:'합성 연구',url:'https://example.org/research'},source_hash:hash,state:'source_review',source_packet:{title:'전파망원경에 AI를 붙인 이유',body:'실제 사실 판정이 아닌 합성 검수입니다. [E999]',quality:{status:'unverified'}},selections:{blog:true,video:false,cards:false,pdf:false},tasks:[],events:[],drafts:[]};
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;if(request.method()!=='GET')writes.push(path);
  let body:any;
  if(path==='/api/session')body={csrf:'synthetic'};
  else if(path==='/api/dashboard')body={articles:[],jobs:[job],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:1000,spent_krw:0,reserved_krw:0,remaining_krw:1000},window:{status:'closed'},provider:{configured:false},knowledge:{}};
  else if(path==='/api/jobs/summaries')body={jobs:[job]};
  else if(path===`/api/jobs/${id}`)body=job;
  else if(path.endsWith('/content-diagnostics')){
   if(!valid && initial==='unavailable'){await route.fulfill({status:503,json:{detail:'구성 정보를 불러오지 못했습니다'}});return;}
   body={source_hash:valid?hash:'old-source',analysis:{blog:[{id:'citations',label:'인용 ID가 등록 근거에 연결됨',passed:false,detail:valid?'미등록: E999':'이전 판본 결과'}],social:{},note:'기계적 구성 정보'}};
  }
  await route.fulfill({status:body===undefined?404:200,json:body??{detail:'합성 시험 범위 밖'}});
 });
 await page.setViewportSize({width,height:1000});await page.goto(`/scripts/${id}`);
 const panel=page.getByRole('group',{name:'저장된 원고 구성 점검'});
 await panel.locator('summary').focus();await page.keyboard.press('Enter');await expect(panel).toHaveAttribute('open','');
 await expect(panel.getByRole('alert')).toBeVisible();await expect(panel).not.toContainText('이전 판본 결과');
 valid=true;await panel.getByRole('button',{name:'구성 정보 다시 조회'}).click();
 await expect(panel.getByRole('region',{name:'블로그 구성 항목'})).toContainText('미등록: E999');
 await expect(panel.getByRole('alert')).toHaveCount(0);await expect(panel).toContainText('미저장 문장은 포함하지 않습니다');
 await expect(panel.getByRole('button')).toHaveCount(1);
 expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 expect(writes).toEqual([]);expect(errors).toEqual([]);
});
