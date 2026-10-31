import {test,expect,type Page} from '@playwright/test';

async function harness(page:Page) {
  const hash='a'.repeat(64),id='thumbnail-contract';let revision=1;
  let state:any={revision:'1'.repeat(64),current_source_hash:hash,source_hash:hash,stale:false,title:'합성 검증 원고',candidates:[1,2,3].map(n=>({id:String(n),title:'합성 검증 원고',angle:`방향 ${n}`,url:`/api/thumbnail-contract/image-${n}`,provenance:{provider:'synthetic-test'}}))};
  const job={id,title:'합성 검증 원고',state:'source_review',source_hash:hash,article:{id:'one',title:'합성 시험',url:'https://example.com'},selections:{blog:false,video:true,pdf:false,cards:false},source_packet:{title:'합성 검증 원고',body:'합성 화면 시험입니다. 실제 콘텐츠가 아닙니다.',video:{scenes:[]},quality:{status:'pending'}},tasks:[],events:[],drafts:[]};
  const dashboard={articles:[],jobs:[job],feeds:[],agents:[],tasks:[],events:[],budget:{cap_krw:10000,spent_krw:0,reserved_krw:0,remaining_krw:10000},window:{status:'open',authorized_end:new Date(Date.now()+3600000).toISOString()},provider:{model:'synthetic',configured:false},knowledge:{}};
  const writes:{path:string;body:any;csrf?:string}[]=[];
  await page.route('**/api/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(path.startsWith('/api/thumbnail-contract/image-'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#2d4d39"/></svg>'});
    if(request.method()!=='GET')writes.push({path,body:request.postDataJSON(),csrf:request.headers()['x-office-csrf']});
    let response:any;
    if(path.endsWith('/thumbnail-studio/choose')){const body=request.postDataJSON();state={...state,selected_id:body.candidate_id,finalized_id:body.finalize?body.candidate_id:null,revision:(++revision).toString().repeat(64)};response=state;}
    else if(path.endsWith('/thumbnail-studio/generate')){state={...state,candidates:[...state.candidates,{id:'edited',title:state.title,angle:'수정본',url:'/api/thumbnail-contract/image-4',parent_id:state.selected_id,instruction:request.postDataJSON().instruction}],revision:(++revision).toString().repeat(64)};response={id:'synthetic-task',state:'completed'};}
    else if(path.endsWith('/thumbnail-studio'))response=state;
    else if(path.endsWith('/deliveries'))response={deliveries:[],youtube_configured:false};
    else if(path==='/api/newsletters')response={issues:[]};
    else if(path==='/api/channels')response={channels:[]};
    else if(path==='/api/session')response={csrf:'synthetic-token'};
    else if(path==='/api/dashboard')response=dashboard;
    else if(path==='/api/jobs/summaries')response={jobs:[job]};
    else if(path===`/api/jobs/${id}`)response=job;
    else if(path.endsWith('/production-estimate'))response={clips:{paid:false},thumbnail_artwork:true};
    await route.fulfill({status:response===undefined?404:200,contentType:'application/json',body:JSON.stringify(response??{detail:'Synthetic fixture endpoint intentionally unavailable'})});
  });
  return writes;
}

for(const width of [1440,375])test(`썸네일 ${width}px 비교·확대·참조수정·최종 결정 계약`,async({page})=>{
  const writes=await harness(page);await page.setViewportSize({width,height:1000});await page.goto('/publish?job=thumbnail-contract');
  const panel=page.getByRole('region',{name:'썸네일 3장을 비교하고 다듬으세요'});
  await expect(panel.getByRole('button',{name:'이 이미지 선택',exact:true})).toHaveCount(3);
  await panel.getByRole('button',{name:'후보 1 크게 보기',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'썸네일 크게 보기'})).toBeVisible();await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog',{name:'썸네일 크게 보기'})).toHaveCount(0);
  await panel.getByRole('button',{name:'이 이미지 선택',exact:true}).first().click();
  const edit=panel.getByLabel('선택 이미지에서 바꾸고 싶은 부분',{exact:true});await expect(edit).toBeVisible();
  expect(await edit.evaluate(e=>parseFloat(getComputedStyle(e).fontSize))).toBeGreaterThanOrEqual(16);
  await edit.fill('인물과 구도는 유지하고 빛만 부드럽게');
  await panel.getByRole('checkbox',{name:/OpenAI 이미지 비용 확인/}).check();
  await panel.getByRole('button',{name:'선택 이미지 수정본 만들기',exact:true}).click();
  await expect(panel.getByRole('button',{name:'이 이미지 선택',exact:true})).toHaveCount(3);
  await panel.getByRole('button',{name:'이 이미지 선택',exact:true}).last().click();
  await expect(panel.getByAltText('수정 전 선택 이미지')).toBeVisible();await expect(panel.getByAltText('수정한 이미지')).toBeVisible();
  const final=panel.getByRole('button',{name:'이 이미지를 최종 썸네일로 확정',exact:true});await expect(final).toBeDisabled();
  await panel.getByRole('checkbox',{name:'선택한 이미지의 제목·내용·권리를 확인했습니다.',exact:true}).check();await final.click();
  await expect(panel.getByText('최종 확정',{exact:true})).toBeVisible();
  expect(writes.find(w=>w.path.endsWith('/generate'))?.body).toMatchObject({source_hash:'a'.repeat(64),edit_id:'1',instruction:'인물과 구도는 유지하고 빛만 부드럽게',confirm_paid:true});
  expect(writes.at(-1)?.body).toMatchObject({candidate_id:'edited',finalize:true});
  expect(writes.every(w=>w.path.includes('/thumbnail-studio/')&&w.csrf==='synthetic-token')).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
