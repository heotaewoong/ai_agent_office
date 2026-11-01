import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import {test} from 'node:test';
const B=createRequire(import.meta.url)('../vendor/babylon.min.js');
const source=await readFile(new URL('../app.js',import.meta.url),'utf8');
const start=source.indexOf('    prepareSsaoDepthGuard('),end=source.indexOf('\n    },',start);
assert(start>=0&&end>start,'SSAO guard installer must be available');
const make=(shader,version=B.Engine.Version,phone=false)=>{
  const store={ssao2PixelShader:shader};
  return {store,install:Function('B','isPhone',`return ({${source.slice(start,end+6)}}).prepareSsaoDepthGuard`)({Engine:{Version:version},Effect:{ShadersStore:store}},()=>phone)};
};

test('the bundled shader retains the near-depth path and its original far-depth expression',()=>{
  const original=B.Effect.ShadersStore.ssao2PixelShader,f=make(original);
  assert.equal(f.install(),true);
  const patched=f.store.ssao2PixelShader;
  const guard='if(depth>=maxZ){gl_FragColor=vec4(vec3(clamp(1.0+base,0.0,1.0)),1.0);return;}';
  assert.equal(patched.replace(guard,''),original,'no normal, sample, blur or combine logic may change');
  assert(patched.indexOf(guard)>patched.indexOf('depth=depth*depthSign;'));
  assert(patched.indexOf(guard)<patched.indexOf('vec3 normal='));
  assert.equal(f.install(),true);assert.equal(f.store.ssao2PixelShader,patched,'idempotent installation');
});

test('mobile keeps the original shader because its performance gain was not consistent',()=>{
  const original=B.Effect.ShadersStore.ssao2PixelShader,f=make(original,B.Engine.Version,true);
  assert.equal(f.install(),false);assert.equal(f.store.ssao2PixelShader,original);
});

test('unsupported shader text falls back without modifying it',()=>{
  for(const text of [undefined,'changed upstream shader','depth=depth*depthSign;']) {
    const f=make(text);assert.equal(f.install(),false);assert.equal(f.store.ssao2PixelShader,text);
  }
  const future=make(B.Effect.ShadersStore.ssao2PixelShader,'8.0.0');
  assert.equal(future.install(),false);assert.equal(future.store.ssao2PixelShader,B.Effect.ShadersStore.ssao2PixelShader);
});

test('at and beyond maxZ the existing fade has exactly the same constant output',()=>{
  const clamp=x=>Math.max(0,Math.min(1,x));
  for(const maxZ of [1,80,160,1000])for(const depth of [maxZ,maxZ+1,maxZ*10])
    for(const base of [-.2,0,.08,.3])for(const occlusion of [0,.5,8,16]) {
      const t=clamp((depth-maxZ*.75)/(maxZ*.25)),fade=1-t*t*(3-2*t);
      assert.equal(clamp(1-1.1*occlusion*fade/16+base),clamp(1+base));
    }
});
