const fs = require('node:fs');
const path = require('node:path');
const {bundle} = require('@remotion/bundler');
const {openBrowser, selectComposition, renderStill, renderMedia} = require('@remotion/renderer');
(async () => {
  const dir = path.resolve(process.argv[2]);
  if (process.platform !== 'linux' || !dir.startsWith('/home/ubuntu/.local/state/heobrain-content-office/artifacts/'))
    throw Error('EC2 artifact output required');
  const chrome = process.env.CHROME_PATH;
  const layoutOnly=process.argv.includes('--layout-only');
  if (!chrome || !fs.existsSync(chrome)) throw Error('Installed Chromium required');
  const available = () => {const d=fs.statfsSync(dir); return d.bavail*d.bsize;};
  if (available() < 400 * 1024**2) throw Error('Insufficient disk for bounded render');
  const marker=path.join(dir,layoutOnly?'caption-layout-started-v2.json':'caption-full-render-started.json');
  fs.writeFileSync(marker,JSON.stringify({started:new Date().toISOString(),
    scriptSha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(__filename)).digest('hex')}),{flag:'wx'});
  const cues=JSON.parse(fs.readFileSync(path.join(dir,'cues.json')));
  if(cues.length!==31) throw Error('Unexpected cue count');
  const serveUrl=await bundle({entryPoint:path.join(dir,'CaptionPanel.tsx'),
    outDir:path.join(dir,layoutOnly?'bundle-layout-v2':'bundle'),enableCaching:false,symlinkPublicDir:true});
  const browser=await openBrowser('chrome',{browserExecutable:chrome});
  try {
    const c=await selectComposition({serveUrl,id:'CaptionPanel',puppeteerInstance:browser});
    if(c.durationInFrames!==3552 || c.width!==1080 || c.height!==660) throw Error('Unexpected composition');
    const layouts=new Map();
    const violations=[];
    const onBrowserLog=(log)=>{const prefix='__CAPTION_LAYOUT__';if(log.text.startsWith(prefix)){
      const x=JSON.parse(log.text.slice(prefix.length));layouts.set(x.cue,x);
      if(x.left<84 || x.right>926 || x.top<150 || x.bottom>530 || x.height<30) violations.push(x);
    }};
    for(let i=0;i<cues.length;i++) {
      const frame=Math.round((cues[i].start+cues[i].end)*12);
      await renderStill({serveUrl,composition:c,puppeteerInstance:browser,frame,imageFormat:'jpeg',jpegQuality:85,
        output:path.join(dir,`${layoutOnly?"cue-layout-v2":"cue"}-${String(i+1).padStart(2,'0')}.jpg`),onBrowserLog});
    }
    if(layouts.size!==31)throw Error('Missing layout evidence');
    if(violations.length){fs.writeFileSync(path.join(dir,'layout-violations.json'),JSON.stringify(violations));throw Error('Caption outside safe region');}
    fs.writeFileSync(path.join(dir,'caption-layout-audit.json'),JSON.stringify({count:layouts.size,
      all_safe:true,panel_position_y:1220,absolute_text_bottom_limit:1750,items:[...layouts.values()]},null,2));
    if(layoutOnly) return;
    let last=-1;
    await renderMedia({serveUrl,composition:c,puppeteerInstance:browser,codec:'h264',crf:20,
      concurrency:1,outputLocation:path.join(dir,'caption-panel-full.mp4'),onBrowserLog,
      onProgress:p=>{const step=Math.floor(p.progress*20);if(step!==last){last=step;
        fs.writeFileSync(path.join(dir,'caption-full-progress.json'),JSON.stringify({progress:p.progress,
          renderedFrames:p.renderedFrames,encodedFrames:p.encodedFrames,availableBytes:available()}));}}});
    fs.writeFileSync(path.join(dir,'caption-full-render-complete.json'),JSON.stringify({frames:3552,fps:24,
      duration:148,renderer:require('remotion/package.json').version,caption_cues:31}),{flag:'wx'});
  } finally {await browser.close({silent:true});}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
