import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const B = createRequire(import.meta.url)('../vendor/babylon.min.js');
const source = await readFile(new URL('../app.js', import.meta.url), 'utf8');
function method(name, globals = {}) {
  const start = source.indexOf('    ' + name + '(', source.indexOf('  const world = {'));
  const end = source.indexOf('\n    },', start);
  assert(start >= 0 && end > start, `world.${name} must exist`);
  return Function(...Object.keys(globals), 'return ({' + source.slice(start, end + 6) + '}).' + name)(...Object.values(globals));
}
const planFor = quality => method('architecturePlan', { QUALITY: quality });
const walkable = method('walkable', { space: { layer: 'office', stages: [] }, workshop:{collides:()=>false}, ISLAND_W: 18, ISLAND_D: 16 });
const canWalk = (obstacles, x, z) => walkable.call({ officeObstacles: obstacles, heightAt: () => 0 }, { x, z }, 0);

function corners(part) {
  const [w, h, d] = part.size, [x, y, z] = part.position;
  const c = Math.cos(part.rotationZ), s = Math.sin(part.rotationZ), points = [];
  for (const dx of [-w / 2, w / 2]) for (const dy of [-h / 2, h / 2]) for (const dz of [-d / 2, d / 2]) {
    points.push(new B.Vector3(x + dx * c - dy * s, y + dx * s + dy * c, z + dz));
  }
  return points;
}
function extent(points) {
  const result = { min: points[0].clone(), max: points[0].clone() };
  for (const point of points.slice(1)) { result.min.minimizeInPlace(point); result.max.maximizeInPlace(point); }
  return result;
}
const overlaps = (a, b) => ['x', 'y', 'z'].every(axis => a.min[axis] < b.max[axis] && a.max[axis] > b.min[axis]);

function fixture(quality = 'high') {
  const engine = new B.NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64 });
  const scene = new B.Scene(engine), light = new B.DirectionalLight('test-sun', new B.Vector3(0, -1, 1), scene);
  const shadows = new B.ShadowGenerator(128, light);
  const world = {
    scene, matCache: new Map(), architecturePlan: planFor(quality),
    mat: method('mat', { B }), pbr: method('pbr', { B, QUALITY: quality }),
    buildArchitecture: method('buildArchitecture', { B }),
    castShadow: mesh => shadows.addShadowCaster(mesh, false),
    receiveShadow: mesh => { mesh.receiveShadows = true; },
  };
  return { world, scene, shadows, dispose() { scene.dispose(); engine.dispose(); } };
}

test('arrival footings are covered by collision circles and the spawn-to-portal corridor stays open', () => {
  const { parts, obstacles } = planFor('high')('arrival');
  assert.equal(obstacles.length, 2);
  for (const part of parts.filter(p => p.name === 'footing')) {
    const obstacle = obstacles.find(o => o.x === part.position[0] && o.z === part.position[2]);
    assert(obstacle, 'each footing needs its own collision circle');
    for (const p of corners(part)) assert(Math.hypot(p.x - obstacle.x, p.z - obstacle.z) <= obstacle.r);
    assert.equal(canWalk(obstacles, obstacle.x, obstacle.z), false);
    assert.equal(canWalk(obstacles, obstacle.x + Math.sign(obstacle.x) * (obstacle.r + .41), obstacle.z), true);
  }
  for (let z = -62; z <= -38; z += .5) for (let x = -3; x <= 3; x += .5) {
    assert.equal(canWalk(obstacles, x, z), true, `passage blocked at ${x},${z}`);
  }
  const passage = { min: new B.Vector3(-3, 0, -62), max: new B.Vector3(3, 4.8, -38) };
  for (const part of parts) assert(!overlaps(extent(corners(part)), passage), `${part.name} blocks the arrival view`);
});

test('arrival architecture clears the existing portal, base, and lift rails', () => {
  const ringRadius = 5.2 / 2 + .45 / 2;
  const fixtures = [
    { min: new B.Vector3(-ringRadius, 3 - ringRadius, -46 - .225), max: new B.Vector3(ringRadius, 3 + ringRadius, -46 + .225) },
    { min: new B.Vector3(-4, -.05, -50), max: new B.Vector3(4, .25, -42) },
  ];
  for (const x of [-3, 3]) for (const z of [-49, -43]) fixtures.push({
    min: new B.Vector3(x - .14, -82, z - .14), max: new B.Vector3(x + .14, 1, z + .14),
  });
  for (const part of planFor('high')('arrival').parts) for (const fixture of fixtures) {
    assert(!overlaps(extent(corners(part)), fixture), `${part.name} overlaps the existing lift`);
  }
});

test('atrium additions at walking height stay behind the existing blocked walls', () => {
  const plan = planFor('high')('atrium');
  assert.deepEqual(plan.obstacles, []);
  for (const part of plan.parts.filter(p => extent(corners(p)).min.y < 3.2)) {
    for (const point of corners(part)) assert(point.z < -5.3 || point.x < -5.8, `${part.name} intrudes into the existing room`);
  }
});

test('low and high architecture preserve collision and clearance while only rib density changes', () => {
  for (const kind of ['arrival', 'atrium']) {
    const low = planFor('low')(kind), high = planFor('high')(kind);
    assert.deepEqual(low.obstacles, high.obstacles);
    assert.deepEqual(low.parts.filter(p => p.name !== 'roof-rib'), high.parts.filter(p => p.name !== 'roof-rib'));
    assert(low.parts.filter(p => p.name === 'roof-rib').length < high.parts.filter(p => p.name === 'roof-rib').length);
  }
});

test('real Babylon geometry merges into four non-pickable materials and excludes lights from shadows', () => {
  const f = fixture();
  try {
    for (const kind of ['arrival', 'atrium']) {
      const result = f.world.buildArchitecture(kind);
      assert.equal(result.meshes.length, 4);
      assert.equal(new Set(result.meshes.map(m => m.material)).size, 4);
      assert.deepEqual(result.obstacles, f.world.architecturePlan(kind).obstacles);
      assert.equal(f.scene.meshes.length, 4, 'source boxes must be disposed after merging');
      for (const mesh of result.meshes) {
        assert.equal(mesh.isPickable, false);
        const light = mesh.name.endsWith('-light');
        assert.equal(f.shadows.getShadowMap().renderList.includes(mesh), !light);
        assert.equal(mesh.receiveShadows, !light);
      }
      result.meshes.forEach(m => m.dispose());
    }
  } finally { f.dispose(); }
});

test('translated and rotated parent transforms merged vertices exactly once and remains movable', () => {
  const f = fixture();
  try {
    for (const kind of ['arrival', 'atrium']) {
      const parent = new B.TransformNode('stage', f.scene);
      parent.position.set(31, 4, -17); parent.rotation.y = .73;
      const { meshes } = f.world.buildArchitecture(kind, parent);
      for (const shift of [0, 11]) {
        parent.position.x = 31 + shift; const transform = parent.computeWorldMatrix(true);
        for (const mesh of meshes) {
          assert.equal(mesh.parent, parent);
          const material = mesh.name.split('-').at(-1), actual = [];
          const positions = mesh.getVerticesData(B.VertexBuffer.PositionKind), world = mesh.computeWorldMatrix(true);
          for (let i = 0; i < positions.length; i += 3) actual.push(B.Vector3.TransformCoordinates(B.Vector3.FromArray(positions, i), world));
          const expected = f.world.architecturePlan(kind).parts.filter(p => p.material === material)
            .flatMap(corners).map(p => B.Vector3.TransformCoordinates(p, transform));
          for (const [points, candidates] of [[actual, expected], [expected, actual]]) for (const point of points) {
            assert(candidates.some(p => B.Vector3.Distance(point, p) < 1e-4), `${kind}/${material} has a baked or stale parent transform`);
          }
        }
      }
      parent.dispose(); assert.equal(f.scene.meshes.length, 0);
    }
  } finally { f.dispose(); }
});

test('repeated architecture rebuilds dispose geometry and reuse four materials and two surface textures', () => {
  const f = fixture();
  let textureCount;
  try {
    for (let i = 0; i < 3; i++) {
      const parent = new B.TransformNode('stage', f.scene), arrival = f.world.buildArchitecture('arrival');
      const atrium = f.world.buildArchitecture('atrium', parent);
      assert.equal(f.scene.meshes.length, 8);
      assert.equal(f.world.matCache.size, 4); assert.equal(f.scene.materials.length, 4);
      assert.equal(f.world.surfaceTextures.size, 2);
      textureCount ??= f.scene.textures.length;
      assert.equal(f.scene.textures.length, textureCount, 'lazy shadow textures must also stabilize after the first build');
      for (const texture of f.world.surfaceTextures.values()) assert(f.scene.textures.includes(texture));
      arrival.meshes.forEach(m => m.dispose()); parent.dispose();
      assert([...arrival.meshes, ...atrium.meshes].every(m => m.isDisposed()));
      assert.equal(f.scene.meshes.length, 0); assert.equal(f.scene.transformNodes.length, 0);
      assert.equal(f.shadows.getShadowMap().renderList.length, 0, 'disposed architecture must leave the shadow list');
      assert.equal(f.scene.materials.length, 4, 'shared material cache must survive a geometry rebuild');
    }
  } finally { f.dispose(); }
});
