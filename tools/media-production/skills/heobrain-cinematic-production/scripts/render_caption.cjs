// An opt-in silent 8-second proof, not a full-film worker or publishing tool.
const fs = require('node:fs');
const path = require('node:path');
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderStill, renderMedia} = require('@remotion/renderer');

(async () => {
  const dir = path.resolve(process.argv[2]);
  const chrome = process.env.CHROME_PATH;
  if (process.platform !== 'linux' || !dir.startsWith('/home/ubuntu/.local/state/heobrain-content-office/artifacts/'))
    throw Error('EC2 artifact output required');
  if (!chrome || !fs.existsSync(chrome)) throw Error('Installed Chromium required');
  const marker = path.join(dir, 'caption-render-started-v2.json');
  fs.writeFileSync(marker, JSON.stringify({started: new Date().toISOString(),
    scriptSha256: require('node:crypto').createHash('sha256').update(fs.readFileSync(__filename)).digest('hex')}), {flag: 'wx'});
  const serveUrl = await bundle({entryPoint: path.join(dir, 'CaptionPilot.tsx'),
    publicDir: path.join(dir, 'public'), outDir: path.join(dir, 'bundle-v2'),
    enableCaching: false, symlinkPublicDir: true});
  const c = await selectComposition({serveUrl, id: 'CaptionPilot', browserExecutable: chrome});
  if (c.durationInFrames !== 192 || c.width !== 1080 || c.height !== 1920) throw Error('Unexpected pilot size');
  for (const frame of [12, 30, 72, 110, 150])
    await renderStill({serveUrl, composition: c, browserExecutable: chrome, frame,
      output: path.join(dir, `caption-${frame}.png`), timeoutInMilliseconds: 90000});
  await renderMedia({serveUrl, composition: c, browserExecutable: chrome, codec: 'h264', crf: 21,
    concurrency: 1, offthreadVideoCacheSizeInBytes: 16000000,
    outputLocation: path.join(dir, 'caption-silent-v2.mp4'), timeoutInMilliseconds: 90000});
  fs.writeFileSync(path.join(dir, 'caption-render-complete.json'), JSON.stringify({frames:192,fps:24,duration:8,
    renderer: require('remotion/package.json').version, sourceSeconds:[8,16], audioMuxPending:true}), {flag:'wx'});
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
