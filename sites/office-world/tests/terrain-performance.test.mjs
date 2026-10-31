import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const B = createRequire(import.meta.url)('../vendor/babylon.min.js');
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
const start = source.indexOf('    buildMeadowSurface('), end = source.indexOf('\n    },', start);
const surface = Function('B', 'return ({' + source.slice(start, end + 6) + '}).buildMeadowSurface')(B);
function template(scene, name = 'terrain') {
  const uv = [1, 1, 1, 1, 0, 2].map(t => new B.Vector4(t / 3, 0, (t + 1) / 3, 1));
  return B.MeshBuilder.CreateBox(name, { size: 1, faceUV: uv, wrap: true }, scene);
}

test('flat terrain removes only covered sides and retains top, bottom, edge, atlas and material', () => {
  const engine = new B.NullEngine(), scene = new B.Scene(engine), mesh = template(scene);
  const material = new B.StandardMaterial('grass', scene); mesh.material = material;
  try {
    const originalUV = mesh.getVerticesData(B.VertexBuffer.UVKind);
    const result = surface.call({ meadowHeight: () => -83 }, mesh, 8, 8);
    assert.deepEqual(result, { cells: 4, faces: 16 });
    assert.equal(mesh.material, material); assert.equal(mesh.isPickable, false);
    const bounds = mesh.getBoundingInfo().boundingBox;
    assert.deepEqual(bounds.minimum.asArray(), [-8, -91, -8]);
    assert.deepEqual(bounds.maximum.asArray(), [8, -83, 8]);
    const uv = mesh.getVerticesData(B.VertexBuffer.UVKind), normals = mesh.getVerticesData(B.VertexBuffer.NormalKind);
    for (let i = 0; i < uv.length / 8; i++) {
      const normal = normals.slice(i * 12, i * 12 + 3);
      // Box face ordering is checked against the untouched runtime template.
      const ref = template(scene, 'uv-reference');
      const rn = ref.getVerticesData(B.VertexBuffer.NormalKind);
      const index = [0,1,2,3,4,5].find(f => normal.every((v,j) => Math.abs(v-rn[f*12+j])<1e-6));
      assert.notEqual(index, undefined);
      assert(uv.slice(i*8,i*8+8).every((value,j) => Math.abs(value-originalUV[index*8+j]) < 1e-6)); ref.dispose();
    }
  } finally { scene.dispose(); engine.dispose(); }
});

test('unequal terrain heights preserve every exposed step and exterior ray hit', () => {
  const engine = new B.NullEngine(), scene = new B.Scene(engine), mesh = template(scene);
  const height = (x,z) => -83 + (x >= 0 ? 2 : 0) + (z >= 0 ? 1 : 0), originals = [];
  try {
    for (const x of [-4,4]) for (const z of [-4,4]) {
      const box = template(scene, `reference-${x}-${z}`); box.scaling.set(8,8,8); box.position.set(x,height(x,z)-4,z); box.computeWorldMatrix(true); originals.push(box);
    }
    const result = surface.call({ meadowHeight: height }, mesh, 8, 8); mesh.isPickable = true;
    assert.equal(result.faces,24,'no fully covered sides at different heights');
    const rays = [];
    for (const x of [-7,-3,3,7]) for (const z of [-7,-3,3,7]) rays.push(new B.Ray(new B.Vector3(x,0,z),new B.Vector3(0,-1,0),200));
    for (const y of [-90,-84,-82,-81]) for (const z of [-6,6]) rays.push(new B.Ray(new B.Vector3(-20,y,z),new B.Vector3(1,0,0),50));
    for (const ray of rays) {
      const before = scene.pickWithRay(ray,m=>originals.includes(m));
      const after = scene.pickWithRay(ray,m=>m===mesh);
      assert.equal(after.hit,before.hit);
      if(before.hit) assert(B.Vector3.Distance(after.pickedPoint,before.pickedPoint)<1e-5);
    }
    assert.throws(()=>surface.call({meadowHeight:height},mesh,0,8));
    assert.throws(()=>surface.call({meadowHeight:height},mesh,3,8));
  } finally { scene.dispose(); engine.dispose(); }
});

test('actual high-quality terrain retains all cells while cutting submitted triangles by over half', () => {
  const engine = new B.NullEngine(), scene = new B.Scene(engine), mesh = template(scene);
  const method = name => {
    const a = source.indexOf('    ' + name + '('), b = source.indexOf('\n    },', a);
    return Function('return ({' + source.slice(a,b+6) + '}).' + name)();
  };
  try {
    const context = { meadowCell:8, groundRoadHeight:method('groundRoadHeight'), meadowHeight:method('meadowHeight') };
    const result = surface.call(context, mesh, 8);
    assert.equal(result.cells,40000);
    assert(result.faces < result.cells*3);
    assert.equal(mesh.getTotalIndices(),result.faces*6);
    console.log(JSON.stringify({terrainGeometry:{...result,baselineFaces:240000,submittedVerticesBefore:960000,submittedVerticesAfter:mesh.getTotalVertices(),indicesBefore:1440000,indicesAfter:mesh.getTotalIndices()}}));
  } finally { scene.dispose(); engine.dispose(); }
});

test('devices without 32-bit indices keep the original instanced terrain', () => {
  const engine = new B.NullEngine(), scene = new B.Scene(engine), mesh = template(scene);
  try {
    const result = surface.call({ engine: { getCaps: () => ({ uintIndices: false }) }, meadowHeight: () => -83 }, mesh, 8, 8);
    assert.deepEqual(result, { cells: 4, faces: 24 });
    assert.equal(mesh.getTotalVertices(), 24);
    assert.equal(mesh.thinInstanceCount, 4);
    assert.equal(mesh.isPickable, false);
    const matrices = mesh.thinInstanceGetWorldMatrices();
    assert.deepEqual(matrices.map(m => m.getTranslation().asArray()), [[-4,-87,-4],[-4,-87,4],[4,-87,-4],[4,-87,4]]);
  } finally { scene.dispose(); engine.dispose(); }
});

test('low-quality terrain retains its compact instanced buffers', () => {
  const engine = new B.NullEngine(), scene = new B.Scene(engine), mesh = template(scene);
  try {
    surface.call({ meadowHeight: () => -83 }, mesh, 16, 16, false);
    assert.equal(mesh.getTotalVertices(), 24);
    assert.equal(mesh.thinInstanceCount, 4);
  } finally { scene.dispose(); engine.dispose(); }
});
