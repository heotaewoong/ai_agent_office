import {chromium} from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import {mkdir,writeFile} from 'node:fs/promises';
const directory='test-results/production';await mkdir(directory,{recursive:true});
const browser=await chromium.launch();const context=await browser.newContext({viewport:{width:1440,height:1050}});const page=await context.newPage();
const errors=[],mutations=[];page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/')&&request.method()!=='GET')mutations.push({method:request.method(),path:new URL(request.url()).pathname});});
const response=await page.goto('http://127.0.0.1:3110');await page.getByRole('checkbox').first().waitFor();
const before=await page.evaluate(async()=>{const r=await fetch('/api/dashboard');return r.json();});
const record={checked_at:new Date().toISOString(),mode:'production',command:'npm run start',http_status:response.status(),views:{},errors,mutations,before_hashes:before.jobs.map(j=>({id:j.id,hash:j.source_hash,state:j.state}))};
for(const [key,name] of [['news','오늘의 뉴스'],['studio','콘텐츠 작업실'],['delivery','제작·출고함'],['activity','운영 기록']]){
 if(key!=='news')await page.getByRole('navigation',{name:'오피스 메뉴'}).getByRole('button',{name:new RegExp('^'+name)}).click();
 const heading=await page.locator('main h1').innerText();if(!heading.includes(name))throw new Error('Unexpected view '+heading);
 record.views[key]={heading,dev_overlay:await page.locator('nextjs-portal').count(),horizontal_overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
 if(key==='studio'){await page.getByLabel('본문 · Markdown').waitFor();record.body_font_px=await page.getByLabel('본문 · Markdown').evaluate(element=>parseFloat(getComputedStyle(element).fontSize));record.active_news_evidence_intake_visible=await page.getByLabel('공개 원문 텍스트').count();}
 if(key==='delivery'&&await page.getByRole('region',{name:'음성 제작 설정'}).count())record.voice_label=await page.getByRole('region',{name:'음성 제작 설정'}).innerText();
 await page.screenshot({path:`${directory}/${key}.png`,fullPage:true});
}
await page.getByRole('button',{name:'과거 문서 검색',exact:true}).click();const drawer=page.getByRole('dialog',{name:'과거 문서 검색'});await drawer.getByLabel('과거 문서 검색어').fill('콘텐츠');await drawer.getByRole('button',{name:'문서 검색',exact:true}).click();await drawer.locator('.knowledge-result').first().waitFor();const a11y=await new AxeBuilder({page}).include('.knowledge-drawer').withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
record.knowledge={summary:await drawer.locator('.knowledge-counts').innerText(),results:await drawer.locator('.knowledge-result').count(),accessibility_violations:a11y.violations.map(item=>item.id)};await page.screenshot({path:`${directory}/knowledge.png`,fullPage:true});await page.keyboard.press('Escape');
record.after_hashes=await page.evaluate(async()=>{const r=await fetch('/api/dashboard');const d=await r.json();return d.jobs.map(j=>({id:j.id,hash:j.source_hash,state:j.state}));});record.news_hashes_unchanged=JSON.stringify(record.before_hashes)===JSON.stringify(record.after_hashes);record.status=errors.length||mutations.length||record.body_font_px<16||record.knowledge.accessibility_violations.length||Object.values(record.views).some(v=>v.dev_overlay||v.horizontal_overflow)?'failed':'passed';await writeFile(`${directory}/smoke.json`,JSON.stringify(record,null,2));console.log(JSON.stringify(record,null,2));await browser.close();if(record.status!=='passed')process.exitCode=1;
