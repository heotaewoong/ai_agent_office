import {test, expect, type Page} from '@playwright/test';

async function harness(page: Page) {
  const items = [
    {id:'video',title:'지난 영상',name:'short.mp4',kind:'video',size_bytes:2048,file_count:1},
    {id:'cards',title:'요약 카드',name:'카드뉴스',kind:'cards',size_bytes:1024,file_count:2},
    {id:'thumb',title:'표지 시안',name:'thumbnail.png',kind:'thumbnail',size_bytes:512,file_count:1},
    {id:'approved',title:'현재 출고본',name:'approved.mp4',kind:'video',size_bytes:4096,file_count:1,protected_reason:'현재 제작·출고에서 사용 중입니다'},
  ].map(i=>({state:'available',protected_reason:'',shared:false,modified_at:'2026-11-07T00:00:00Z',preview_url:`/api/library/items/${i.id}/files/0`,...i}));
  const changes: any[] = [];
  await page.route('**/api/**', async route=>{
    const req=route.request(), path=new URL(req.url()).pathname;
    let body:any={},status=200;
    if(path==='/api/library') body={items,storage:{total_bytes:10240,used_bytes:8192,free_bytes:2048},checked_at:'now'};
    else if(path==='/api/library/quote') body={token:'test-quote',count:req.postDataJSON().ids.length,size_bytes:3072,reclaimable_bytes:2048,shared_files:0};
    else if(path==='/api/library/change') {
      const data=req.postDataJSON();changes.push(data);
      for(const id of data.ids){const item=items.find(i=>i.id===id)!;if(data.action==='purge')items.splice(items.indexOf(item),1);else item.state=data.action==='trash'?'trash':'available';}
      body={state:'completed',action:data.action,count:data.ids.length,deleted_files:0,message:'완료'};
    } else if(path.includes('/api/library/items/')) {
      return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150"><rect width="200" height="150" fill="#58735a"/></svg>'});
    } else if(path==='/api/session') body={csrf:'library-test'};
    else if(path==='/api/dashboard') body={articles:[],jobs:[],feeds:[],agents:[],tasks:[],events:[],budget:{},window:{status:'closed'},provider:{},knowledge:{}};
    else if(path==='/api/jobs/summaries') body={jobs:[]};
    else if(path==='/api/channels') body={channels:[]};
    else {status=404;body={detail:'Synthetic unavailable'};}
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  return changes;
}

for(const width of [1440,390]) test(`보관함 ${width}px 선택 취소·휴지통·복원·영구삭제`,async({page})=>{
  const changes=await harness(page);await page.setViewportSize({width,height:950});await page.goto('/publish');
  const library=page.getByRole('region',{name:'산출물 보관함',exact:true});
  await expect(library.getByRole('heading',{name:'만든 결과물을 한눈에'})).toBeVisible();
  const image=library.locator('article img').first();
  await expect.poll(()=>image.evaluate((el:HTMLImageElement)=>el.complete&&el.naturalWidth>0)).toBe(true);
  expect(await image.evaluate(el=>{const a=el.getBoundingClientRect(),b=el.parentElement!.getBoundingClientRect();return a.width<=b.width+1&&a.height<=b.height+1;})).toBe(true);
  await expect(library.getByRole('checkbox',{name:'현재 출고본 approved.mp4 선택'})).toBeDisabled();
  await library.getByRole('checkbox',{name:'지난 영상 short.mp4 선택'}).check();
  await library.getByRole('checkbox',{name:'요약 카드 카드뉴스 선택'}).check();
  const bar=page.getByRole('region',{name:'선택한 산출물 작업'});await expect(bar).toBeInViewport();
  await page.setViewportSize({width:width===390?1440:390,height:950});
  await expect(library.getByRole('checkbox',{name:'지난 영상 short.mp4 선택'})).toBeChecked();await expect(bar).toBeInViewport();
  await page.setViewportSize({width,height:950});
  await bar.getByRole('button',{name:'휴지통으로',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'휴지통으로 옮길까요?'});await expect(dialog).toContainText('지난 영상');
  await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();expect(changes).toHaveLength(0);
  await bar.getByRole('button',{name:'휴지통으로',exact:true}).click();await dialog.getByRole('button',{name:'휴지통으로 이동',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'휴지통으로 옮겼습니다'})).toBeVisible();expect(changes).toHaveLength(1);
  await library.getByRole('tab',{name:/휴지통/}).click();await library.getByRole('checkbox',{name:'지난 영상 short.mp4 선택'}).check();
  await bar.getByRole('button',{name:'복원',exact:true}).click();await page.getByRole('dialog').filter({hasText:'선택한 산출물을 복원할까요?'}).getByRole('button',{name:'복원하기'}).click();
  await expect(library.getByRole('checkbox',{name:'지난 영상 short.mp4 선택'})).toHaveCount(0);
  await library.getByRole('checkbox',{name:'요약 카드 카드뉴스 선택'}).check();await bar.getByRole('button',{name:'영구삭제 확인'}).click();
  const purge=page.getByRole('dialog',{name:'선택한 파일을 영구삭제할까요?'});await expect(purge).toContainText('2.0 KiB');
  await purge.getByRole('button',{name:'선택 파일 영구삭제'}).click();await expect(library.getByRole('checkbox',{name:'요약 카드 카드뉴스 선택'})).toHaveCount(0);
  expect(changes.map(x=>x.action)).toEqual(['trash','restore','purge']);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('카드 미리보기·키보드 닫기는 상태를 변경하지 않는다',async({page})=>{
  const changes=await harness(page);await page.goto('/publish');
  await page.getByRole('button',{name:'요약 카드 카드뉴스 미리보기',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'요약 카드',exact:true});await expect(dialog.getByRole('img')).toHaveCount(2);
  await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();expect(changes).toHaveLength(0);
});

test('목록 조회 실패는 빈 보관함으로 표시하지 않고 다시 확인할 수 있다',async({page})=>{
  const changes=await harness(page);let failed=true;
  await page.route('**/api/library',route=>route.fulfill({status:failed?503:200,contentType:'application/json',body:JSON.stringify(failed?{detail:'저장소를 확인하지 못했습니다'}:{items:[],storage:{total_bytes:1024,used_bytes:0,free_bytes:1024},checked_at:'now'})}));
  await page.goto('/publish');const library=page.getByRole('region',{name:'산출물 보관함',exact:true});
  await expect(library.getByRole('alert')).toContainText('저장소를 확인하지 못했습니다');
  await expect(library.getByRole('heading',{name:'아직 보관된 산출물이 없습니다.'})).toHaveCount(0);
  failed=false;await library.getByRole('button',{name:'목록 다시 확인'}).click();
  await expect(library.getByRole('heading',{name:'아직 보관된 산출물이 없습니다.'})).toBeVisible();expect(changes).toHaveLength(0);
});
