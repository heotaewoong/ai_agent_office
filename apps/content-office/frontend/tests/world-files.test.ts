import test from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdtemp, mkdir, writeFile, unlink, rmdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { gunzipSync, gzipSync, brotliDecompressSync } from "node:zlib";
import { acceptsWorldGzip, readWorldFile, resolveWorldFile, WORLD_ROOT } from "../lib/world-files.ts";
const root = "/srv/world";
test("빈 경로는 index.html", () => assert.deepEqual(resolveWorldFile(root, undefined), { path: "/srv/world/index.html", type: "text/html; charset=utf-8" }));
test("확장자별 타입", () => {
  assert.equal(resolveWorldFile(root, ["styles.css"])?.type, "text/css; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["app.js"])?.type, "text/javascript; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["data", "space.json"])?.type, "application/json; charset=utf-8");
});
test("상위 경로·알 수 없는 확장자는 거부", () => {
  assert.equal(resolveWorldFile(root, ["..", "secret.md"]), null);
  assert.equal(resolveWorldFile(root, ["README.md"]), null);
  assert.equal(resolveWorldFile(root, ["a/../../x.html"]), null);
});

test("고정 Babylon 번들과 해당 라이선스를 앱 경로에서도 제공", () => {
  assert.equal(resolveWorldFile(root, ["vendor", "babylon.min.js"])?.type, "text/javascript; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["vendor", "LICENSE-babylon.txt"])?.type, "text/plain; charset=utf-8");
  assert.equal(resolveWorldFile(root, ["vendor", "other.txt"]), null);
});

test("gzip 협상은 명시적 거부를 와일드카드보다 우선한다", () => {
  for (const header of ["gzip", "br, gzip;q=0.5", "GZIP; q=1", "*;q=0.2"])
    assert.equal(acceptsWorldGzip(header), true, header);
  for (const header of [null, "", "br", "gzip;q=0", "gzip;q=0, *;q=1", "gzip;q=2", "gzip;q=oops", "xgzip"])
    assert.equal(acceptsWorldGzip(header), false, String(header));
});

for (const name of ["arrival-detail-v2", "atrium-detail-v3", "guide-avatar-v1"]) {
  test(`${name} 압축 응답은 원본과 바이트가 같고 미지원 클라이언트는 원본을 받는다`, async () => {
    const file = resolveWorldFile(WORLD_ROOT, ["assets", name + ".json"])!;
    const plain = await readWorldFile(file, "gzip;q=0, *;q=1");
    const compressed = await readWorldFile(file, "gzip, br");
    assert.equal(plain.encoding, null);
    assert.equal(compressed.encoding, "gzip");
    assert.deepEqual(gunzipSync(compressed.body), plain.body);
    assert(compressed.body.length < plain.body.length * .2);
    assert.deepEqual(plain.body, await readFile(file.path));
    assert.equal(resolveWorldFile(WORLD_ROOT, ["assets", name + ".json.gz"]), null);
  });
}

test("압축본이 없는 기존 파일은 원본으로 제공한다", async () => {
  const file = resolveWorldFile(WORLD_ROOT, ["data", "space.json"])!;
  const result = await readWorldFile(file, "gzip");
  assert.equal(result.encoding, null);
  assert.deepEqual(result.body, await readFile(file.path));
});

test("고정 엔진 gzip은 SRI 대상 원본과 바이트가 같고 라이선스 접근을 유지한다", async () => {
  const file = resolveWorldFile(WORLD_ROOT, ["vendor", "babylon.min.js"])!;
  const original = await readFile(file.path);
  const result = await readWorldFile(file, "gzip");
  assert.equal(result.encoding, "gzip");
  assert.deepEqual(gunzipSync(result.body), original);
  assert(result.body.length < original.length * .3);
  assert.equal(resolveWorldFile(WORLD_ROOT, ["vendor", "babylon.min.js.gz"]), null);
  const license = resolveWorldFile(WORLD_ROOT, ["vendor", "LICENSE-babylon.txt"])!;
  assert.equal((await readWorldFile(license, "gzip")).encoding, null);
});


for(const name of ['app.js','styles.css']) {
  test(`${name} static source is compressed without changing decoded bytes`,async()=>{
    const file=resolveWorldFile(WORLD_ROOT,[name])!;
    const plain=await readWorldFile(file,'gzip;q=0, *;q=1');
    const encoded=await readWorldFile(file,'gzip');
    assert.equal(plain.encoding,null);
    assert.equal(encoded.encoding,'gzip');
    assert.deepEqual(gunzipSync(encoded.body),plain.body);
    assert(encoded.body.length<plain.body.length*.35);
  });
}


test('Brotli engine transport decodes to the exact SRI source and respects quality preferences',async()=>{
 const file=resolveWorldFile(WORLD_ROOT,['vendor','babylon.min.js'])!;
 const original=await readFile(file.path),gz=await readWorldFile(file,'gzip');
 for(const header of ['br, gzip','BR;q=1, gzip;q=0.5','gzip;q=0, *;q=1']) {
  const r=await readWorldFile(file,header);assert.equal(r.encoding,'br',header);
  assert.deepEqual(brotliDecompressSync(r.body),original);assert(r.body.length<gz.body.length*.8);
 }
 for(const header of ['br;q=0, gzip','br;q=0, *;q=1','br;q=0.2,gzip;q=1'])assert.equal((await readWorldFile(file,header)).encoding,'gzip',header);
 assert.equal((await readWorldFile(file,'br;q=0,gzip;q=0')).encoding,null);
 assert.equal(resolveWorldFile(WORLD_ROOT,['vendor','babylon.min.js.br']),null);
});


test('missing optional Brotli sidecar retains gzip or original fallback',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'world-br-test-')),vendor=join(dir,'vendor');
 await mkdir(vendor);const path=join(vendor,'babylon.min.js').replaceAll('\\','/'),body=Buffer.from('const x=1;\n'.repeat(200));
 try {
  await writeFile(path,body);await writeFile(path+'.gz',gzipSync(body));
  const file={path,type:'text/javascript'};
  const gz=await readWorldFile(file,'br, gzip');assert.equal(gz.encoding,'gzip');assert.deepEqual(gunzipSync(gz.body),body);
  const plain=await readWorldFile(file,'br');assert.equal(plain.encoding,null);assert.deepEqual(plain.body,body);
 }finally{await unlink(path);await unlink(path+'.gz');await rmdir(vendor);await rmdir(dir);}
});
