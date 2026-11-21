import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

// Original HeoBrain concept geometry. No remote data, model calls, or operational writes.
export function createSpaceCity(container, { onSelect = () => {}, onReady = () => {}, reducedMotion = false } = {}) {
  if (!container) throw new Error('A scene container is required.');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#071524');
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.setClearColor('#071524');
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.04;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute('aria-label', '루미 중앙 본사와 콘텐츠·마케팅·데이터·개발 오피스 3D 미리보기');
  renderer.domElement.setAttribute('role', 'img');
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none;outline:none';
  container.appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.2, 700);
  const homePosition = new THREE.Vector3(1, 34, 49);
  const homeTarget = new THREE.Vector3(0, 0, 0);
  camera.position.copy(homePosition);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(homeTarget);
  controls.enableDamping = true;
  controls.dampingFactor = 0.085;
  controls.minDistance = 12;
  controls.maxDistance = 180;
  controls.minPolarAngle = 0.18;
  controls.maxPolarAngle = Math.PI / 2.15;
  controls.enablePan = true;
  controls.maxTargetRadius = 28;
  const hemi = new THREE.HemisphereLight('#dae7ff', '#65544e', 1.95);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight('#ffe0b2', 2.9);
  sun.position.set(-14, 30, 17);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -30; sun.shadow.camera.right = 30;
  sun.shadow.camera.top = 30; sun.shadow.camera.bottom = -30;
  sun.shadow.camera.near = 1; sun.shadow.camera.far = 85;
  sun.shadow.normalBias = .035; sun.shadow.bias = -.00015;
  scene.add(sun);
  const rim = new THREE.DirectionalLight('#a3c9ff', 1.6);
  rim.position.set(16, 16, -20); scene.add(rim);

  const materials = {};
  function mat(name, color, roughness = .6, metalness = .1, extra = {}) {
    return materials[name] = new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
  }
  mat('ivory', '#e9dfcb', .46, .13); mat('stone', '#bbb6ad', .86, .05);
  mat('navy', '#23384e', .49, .45); mat('navyDark', '#0f1b2c', .63, .35);
  mat('brass', '#bb9764', .32, .74); mat('wood', '#b98451', .72, .03);
  mat('woodDark', '#6b4633', .83, .02); mat('oak', '#dbc5a5', .68, .04);
  mat('slate', '#52596b', .68, .32); mat('mint', '#83aa97', .73, .06);
  mat('terracotta', '#c87155', .77, .06); mat('coral', '#d89792', .75, .07);
  mat('lilac', '#a69ac7', .67, .1); mat('data', '#b0ccd7', .52, .22);
  mat('blue', '#698cb5', .58, .3); mat('amber', '#d4a364', .7, .15);
  mat('leaf', '#3e7256', .9, .02); mat('leafLight', '#78a579', .9, .01);
  mat('pink', '#e9bbd3', .86, .01); mat('soil', '#393d30', .98, 0);
  mat('skin', '#ddaf88', .8, .01); mat('hair', '#302b33', .9, .01);
  mat('shirt', '#e3dccc', .78, .01); mat('screen', '#203755', .42, .15);
  mat('cyan', '#a5f4ed', .35, .15, { emissive: '#30c7d7', emissiveIntensity: 1.5 });
  mat('goldLight', '#fff0bd', .3, .1, { emissive: '#ffc66d', emissiveIntensity: 1.8 });
  mat('screenLight', '#96ceec', .45, .1, { emissive: '#599ed6', emissiveIntensity: .6 });
  mat('glass', '#b6d9e0', .15, .15, { transparent: true, opacity: .26, depthWrite: false });
  mat('warmGlass', '#f4d19b', .2, .1, { transparent: true, opacity: .24, depthWrite: false, emissive: '#ebaa52', emissiveIntensity: .4 });
  mat('court', '#687d84', .88, .04);
  const geometries = {
    box: new THREE.BoxGeometry(1, 1, 1),
    round: new RoundedBoxGeometry(1, 1, 1, 2, .09),
    cylinder: new THREE.CylinderGeometry(1, 1, 1, 24),
    cone: new THREE.ConeGeometry(1, 1, 20),
    sphere: new THREE.SphereGeometry(1, 12, 8),
    leaf: new THREE.SphereGeometry(1, 8, 6),
    ring: new THREE.TorusGeometry(1, .035, 6, 64),
  };
  const batches = new Map();
  const tmp = new THREE.Object3D();
  const city = new THREE.Group(); scene.add(city);
  let offset = new THREE.Vector3(), zoneScale = 1;
  function add(kind, material, pos, scale = [1,1,1], rotation = [0,0,0]) {
    const geometry = typeof kind === 'string' ? geometries[kind] : kind;
    const materialRef = typeof material === 'string' ? materials[material] : material;
    const key = `${geometry.id}:${materialRef.id}`;
    if (!batches.has(key)) batches.set(key, { geometry, material: materialRef, matrices: [] });
    tmp.position.set(pos[0]*zoneScale + offset.x, pos[1] + offset.y, pos[2]*zoneScale + offset.z);
    tmp.rotation.set(...rotation); tmp.scale.set(scale[0]*zoneScale,scale[1],scale[2]*zoneScale); tmp.updateMatrix();
    batches.get(key).matrices.push(tmp.matrix.clone());
  }
  const box = (m,x,y,z,w,h,d,r=0) => add('round',m,[x,y,z],[w,h,d],[0,r,0]);
  const cyl = (m,x,y,z,r,h) => add('cylinder',m,[x,y,z],[r,h,r]);
  const sphere = (m,x,y,z,sx,sy=sx,sz=sx) => add('sphere',m,[x,y,z],[sx,sy,sz]);
  function tube(points, radius, material, segments = 32) {
    const curve = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)));
    add(new THREE.TubeGeometry(curve, segments, radius, 6, false), material, [0,0,0]);
  }
  function horizontalRing(r, y, material, thickness=.045, x=0,z=0) {
    add(new THREE.TorusGeometry(r, thickness, 6, 96), material, [x,y,z], [1,1,1], [Math.PI/2,0,0]);
  }
  function post(x,z,height=1.05, base=.25) {
    cyl('brass',x,base+height/2,z,.045,height);
    sphere('goldLight',x,base+height,z,.075);
  }
  function plant(x,z,size=.8, blossom=false, base=.45) {
    cyl('ivory',x,base+.19*size,z,.28*size,.38*size);
    cyl('soil',x,base+.39*size,z,.24*size,.025);
    cyl('woodDark',x,base+.85*size,z,.045*size,.9*size);
    for(let i=0;i<5;i++) {
      const a=i*2.4;
      add('leaf',blossom?'pink':i%2?'leaf':'leafLight',[x+Math.cos(a)*.29*size,base+(1.06+i*.09)*size,z+Math.sin(a)*.27*size],[.32*size,.22*size,.43*size],[0,a,-.4]);
    }
  }
  function tree(x,z,size=1,blossom=false,base=.3) {
    cyl('woodDark',x,base+size,z,.075*size,2*size);
    for(let i=0;i<9;i++) {
      const a=i*2.4, r=(i%3)*.22*size;
      add('leaf',blossom?'pink':i%2?'leaf':'leafLight',[x+Math.cos(a)*r,base+(1.82+(i%4)*.18)*size,z+Math.sin(a)*r],[.42*size,.3*size,.46*size],[0,a,.1]);
    }
    cyl('soil',x,base+.03,z,.78*size,.06);
    horizontalRing(.85*size,base+.06,'ivory',.055,x,z);
  }
  function bench(x,z,r=0) {
    box('wood',x,.76,z,1.65,.14,.57,r);
    box('wood',x+Math.sin(r)*.22,1.02,z+Math.cos(r)*.22,1.65,.4,.1,r);
    for(const d of [-.6,.6])box('brass',x+Math.cos(r)*d,.52,z-Math.sin(r)*d,.08,.46,.42,r);
  }
  function chair(x,z,color='navy',r=0,base=.7) {
    const dx=Math.sin(r), dz=Math.cos(r);
    box(color,x,base+.45,z,.62,.16,.62,r);
    box(color,x-dx*.26,base+.82,z-dz*.26,.64,.68,.15,r);
    cyl('slate',x,base+.2,z,.06,.45);
    box('slate',x,base+.02,z,.64,.06,.08,r);
    box('slate',x,base+.02,z,.08,.06,.64,r);
  }
  function person(x,z,r=0,shirt='navy',base=.7) {
    const dx=Math.sin(r),dz=Math.cos(r);
    sphere(shirt,x,base+.85,z,.24,.37,.19);
    sphere('skin',x,base+1.37,z,.17,.2,.17);
    sphere('hair',x,base+1.48,z-.025,.18,.11,.18);
    for (const side of [-1,1]) {
      box('slate',x+side*.13,base+.35,z+.17,.14,.5,.16);
      box('skin',x+side*.29,base+.84,z+dz*.15,.12,.12,.37,r);
    }
  }
  function desk(x,z,color='oak',human=true) {
    box(color,x,1.35,z,1.95,.15,1.02);
    for (const side of [-1,1]) box('ivory',x+side*.75,.98,z,.09,.7,.79);
    box('navy',x,1.83,z-.15,.93,.6,.09);
    box('screenLight',x,1.83,z-.095,.81,.47,.018);
    box('navy',x,1.47,z-.15,.1,.25,.08);
    box('slate',x,1.45,z+.27,.7,.035,.21);
    box('ivory',x+.63,1.47,z+.2,.15,.18,.15);
    for(let k=0;k<4;k++)box(k%2?'data':'ivory',x-.31+k*.17,1.77,z-.081,.1,.06+k*.045,.012);
    chair(x,z+.9,color==='wood'?'terracotta':'navy');
    if(human)person(x,z+.88,0,color==='oak'?'navy':'shirt');
  }
  function shelf(x,z,color='wood',w=2.1) {
    box(color,x,1.94,z,w,2.45,.48);
    for(let row=0;row<3;row++) {
      box('oak',x,.95+row*.68,z+.27,w-.14,.075,.5);
      for(let b=0;b<6;b++) box(['coral','data','ivory','navy','amber','mint'][b],x-w*.39+b*w*.15,1.2+row*.68,z+.04,w*.1,.42-(b%3)*.045,.28);
    }
  }
  function wallDisplay(x,y,z,color='data',w=2.6,h=1.35) {
    box('brass',x,y,z,w+.12,h+.12,.08);
    box(color,x,y,z+.055,w,h,.06);
    for(let i=0;i<5;i++) box(i%2?'ivory':'blue',x-w*.36+i*w*.18,y-.25+(i%3)*.11,z+.095,w*.1,.35+(i%3)*.2,.02);
  }
  function roomShell(cx,cz,accent,floor) {
    offset.set(cx,0,cz); zoneScale=1.1;
    box('navy',0,.15,0,10.9,.8,8.6);
    box('ivory',0,.53,0,10.8,.26,8.5);
    box(floor,0,.71,0,10.15,.13,7.85);
    // Tall rear wall + short side wings keep the working interiors visible.
    box('ivory',0,2.1,-3.9,10.55,2.9,.3);
    box('ivory',-5.18,1.95,-1.65,.27,2.6,4.75);
    box('ivory',5.18,1.95,-1.65,.27,2.6,4.75);
    box('brass',0,3.64,-3.9,10.5,.10,.33);
    box('goldLight',0,3.49,-3.69,10.1,.045,.045);
    box(accent,0,2.03,-3.68,9.9,2.4,.12);
    box('ivory',0,.96,4.07,10.5,.48,.22);
    box('navy',0,.57,4.24,10.5,.16,.12);
    box('cyan',0,.53,4.32,8.9,.035,.035);
    for(const x of [-4.5,-3,-1.5,1.5,3,4.5]) {
      box('glass',x,1.41,4.07,1.35,.65,.045);
      box('brass',x+.71,1.43,4.07,.045,.85,.06);
    }
    box('ivory',0,1.47,4.02,1.26,1.5,.18);
    box('glass',0,1.54,4.16,.8,1.23,.04);
    box('goldLight',-.5,1.52,4.19,.045,1.4,.04);
    box('goldLight',.5,1.52,4.19,.045,1.4,.04);
    for(const x of [-4.6,-3,-1.5,1.5,3,4.6]){
      box('goldLight',x,1.08,4.22,.035,.5,.035);
      box('ivory',x,.83,4.24,1.35,.18,.28);
    }
    box('goldLight',0,3.53,-3.66,9.75,.07,.07);
    // Continuous curved roofline and window arcade unify the independent offices.
    const perimeter=[[-3.7,3.68,4.1],[3.7,3.68,4.1],[4.75,3.68,3.7],[5.22,3.68,2.6],[5.22,3.68,-2.8],[4.72,3.68,-3.8],[3.7,3.68,-4.0],[-3.7,3.68,-4.0],[-4.72,3.68,-3.8],[-5.22,3.68,-2.8],[-5.22,3.68,2.6],[-4.75,3.68,3.7],[-3.7,3.68,4.1]];
    tube(perimeter,.13,'ivory',72);
    tube(perimeter.map(p=>[p[0],p[1]+.14,p[2]]),.045,'brass',72);
    for(const x of [-3.75,3.75]){
      cyl('ivory',x,2.22,4.1,.095,2.8);
      box('glass',x<0?-2.45:2.45,1.85,4.1,2.3,1.35,.035);
      box('brass',x<0?-2.45:2.45,2.58,4.1,2.4,.055,.07);
    }
    tube([[-.66,.9,4.2],[-.66,2.08,4.2],[-.46,2.6,4.2],[0,2.78,4.2],[.46,2.6,4.2],[.66,2.08,4.2],[.66,.9,4.2]],.13,'ivory',32);
    tube([[-.5,1,4.23],[-.5,2.05,4.23],[-.3,2.4,4.23],[0,2.53,4.23],[.3,2.4,4.23],[.5,2.05,4.23],[.5,1,4.23]],.035,'goldLight',28);
    plant(-4.5,-3,.9);plant(4.5,-3,.9);
    plant(-4.6,3.35,.55);plant(4.6,3.35,.55);
  }

  // The single floating platform is shared by all teams.
  cyl('navyDark',0,-1.05,0,22.8,1.55);
  cyl('navy',0,-.28,0,22.9,.26);
  cyl('stone',0,-.06,0,22.55,.25);
  cyl('ivory',0,.08,0,22.4,.09);
  cyl('court',0,.14,0,20.3,.06);
  // Small stone paving modules articulate the courtyard without extra draw calls.
  for(let x=-19.2;x<=19.2;x+=1.2)for(let z=-19.2;z<=19.2;z+=1.2){
    const insideRoom=[[-10.3,-8.4],[10.3,-8.4],[-10.3,8.1],[10.3,8.1]].some(([cx,cz])=>Math.abs(x-cx)<6.2&&Math.abs(z-cz)<4.95);
    if(Math.hypot(x,z)<20.2&&Math.hypot(x,z)>5.7&&!insideRoom)box('stone',x,.19,z,1.15,.045,1.15);
  }
  horizontalRing(22.7,-.52,'cyan',.065);
  horizontalRing(22.5,.18,'brass',.06);
  horizontalRing(20.65,.21,'brass',.035);
  horizontalRing(22.15,1.08,'brass',.045);
  for(let i=0;i<88;i++) {
    const a=i*Math.PI*2/88;
    post(Math.sin(a)*22.15,Math.cos(a)*22.15,.84,.23);
    if(i%4===0) {
      box('navy',Math.sin(a)*22.4,-.8,Math.cos(a)*22.4,.6,.75,.25,a);
      cyl('brass',Math.sin(a)*21.55,.5,Math.cos(a)*21.55,.07,.6);
      sphere('goldLight',Math.sin(a)*21.55,.9,Math.cos(a)*21.55,.14,.2,.14);
    }
    // Fine paving seams make the broad promenade feel constructed.
    box('stone',Math.sin(a)*21.4,.153,Math.cos(a)*21.4,.025,.015,1.45,a);
  }
  for(let i=0;i<10;i++) {
    const a=i*Math.PI*2/10;
    add('cone','navy',[Math.sin(a)*20,-2.4,Math.cos(a)*20],[.7,3,.7],[0,0,Math.PI]);
    sphere('cyan',Math.sin(a)*20,-3.8,Math.cos(a)*20,.2,.12,.2);
  }
  // Wide cross-spokes connect the rooms and central HQ; paths are usable at a glance.
  for(const a of [0,Math.PI/2,Math.PI/4,-Math.PI/4]) {
    box('ivory',0,.25,0,2.1,.25,43,a);
    box('brass',Math.cos(a)*1.02,.4,-Math.sin(a)*1.02,.045,.045,42,a);
    box('brass',-Math.cos(a)*1.02,.4,Math.sin(a)*1.02,.045,.045,42,a);
  }
  for(const [x,z] of [[-4.7,16],[4.7,16],[-18,0],[18,0],[-4.7,-17],[4.7,-17]]) {
    box('ivory',x,.4,z,2.35,.4,1.35);
    box('soil',x,.62,z,2.17,.035,1.18);
    plant(x-.6,z,.65,true,.6);plant(x+.6,z,.65,false,.6);
  }
  // Habitable garden courts occupy the residual wedges instead of bare navy acreage.
  for(const [x,z,r] of [[-7,16.8,-.3],[7,16.8,.3],[-17.5,2,Math.PI/2],[17.5,2,-Math.PI/2],[-5,-17.5,0],[5,-17.5,0]]) {
    box('ivory',x,.28,z,3.7,.2,2.4,r);
    box('soil',x,.4,z,3.4,.06,2.05,r);
    tree(x-.65,z,.9,true,.4);tree(x+.65,z+.12,.8,false,.4);
    plant(x-1.2,z+.6,.65,true,.38);plant(x+1.2,z-.5,.65,false,.38);
    bench(x,z+1.6,r);
  }
  for(const [x,z] of [[-17,-10],[17,-10],[-15,13.5],[15,13.5],[-11,-17],[11,-17]]){
    tree(x,z,1.1,false,.25);plant(x+.7,z+.6,.6,true,.3);plant(x-.6,z+.4,.6,true,.3);
  }

  const centers = {
    hq: new THREE.Vector3(0,1,0), content: new THREE.Vector3(-10.3,1,-8.4),
    marketing: new THREE.Vector3(10.3,1,-8.4),data: new THREE.Vector3(-10.3,1,8.1),
    development: new THREE.Vector3(10.3,1,8.1),
  };
  roomShell(-10.3,-8.4,'terracotta','oak');
  shelf(-3.3,-3.32,'wood',2.05); wallDisplay(.0,2.35,-3.53,'oak',2.8,1.35);
  for(const x of [-2.9,-.45])desk(x,1.0,'oak');
  cyl('wood',1.8,1.35,.6,1.15,.14);cyl('brass',1.8,1,.6,.12,.65);
  for(const [x,z]of[[1.8,2],[3.1,.5],[1.8,-.8]])chair(x,z,'terracotta');
  // Recording corner: acoustic slats, camera tripod, softbox, microphone.
  for(let i=0;i<10;i++)box('wood',2.6+i*.23,2.05,-3.5,.085,2.45,.15);
  cyl('slate',3.2,1.55,-1.8,.035,1.6);box('navy',3.2,2.35,-1.8,.55,.37,.35);
  add('cylinder','slate',[3.2,2.35,-1.56],[.14,.23,.14],[Math.PI/2,0,0]);
  box('ivory',4.15,2.5,-1.2,.65,.85,.12,-.25);cyl('slate',4.15,1.5,-1.2,.025,1.7);
  box('mint',1.2,.83,-1.8,2,.07,1.3); plant(4,2.6,.85);
  shelf(-1.1,-3.32,'wood',1.65);
  box('terracotta',3.8,1.12,2.3,1.3,.6,.82);box('terracotta',3.8,1.55,2.62,1.3,.6,.18);
  cyl('wood',2.7,1.22,2.6,.42,.1);cyl('brass',2.7,.96,2.6,.06,.5);
  box('oak',-4.5,1.25,-.8,.45,1.15,2.25);
  for(let i=0;i<7;i++)box(['coral','navy','ivory','mint'][i%4],-4.49,1.92,-1.64+i*.24,.28,.21+(i%3)*.05,.16);

  roomShell(10.3,-8.4,'coral','ivory');
  wallDisplay(-1.4,2.2,-3.52,'lilac',3.7,1.55);shelf(3.65,-3.35,'ivory',1.65);
  box('coral',-2.65,1.15,-1.95,2.6,.65,.9);box('lilac',-2.65,1.65,-2.3,2.65,.72,.23);
  box('brass',-2.65,.87,-1.9,2.5,.12,1);
  cyl('oak',-1.7,1.22,.15,1,.1);cyl('brass',-1.7,.95,.15,.08,.5);
  chair(-2.9,.1,'lilac',-Math.PI/2);chair(-1.7,1.4,'coral');
  desk(1.5,1.4,'ivory');desk(3.7,1.4,'ivory',false);
  cyl('brass',1.4,1.0,-1.8,1.25,.23);cyl('ivory',1.4,1.14,-1.8,1.14,.05);
  for(let i=0;i<3;i++)box(['lilac','coral','data'][i],.7+i*.65,1.53,-1.8,.38,.72-i*.14,.38);
  horizontalRing(1.22,1.15,'goldLight',.035,1.4,-1.8);
  wallDisplay(1.35,2.8,-3.53,'oak',1.7,.8);
  for(let i=0;i<3;i++){
    cyl('ivory',-4.1+i*.7,1.05,2.55,.28,.55);
    box(['coral','lilac','mint'][i],-4.1+i*.7,1.58,2.55,.32,.55,.32);
    horizontalRing(.28,1.34,'goldLight',.025,-4.1+i*.7,2.55);
  }
  plant(4.3,-.3,.65);box('ivory',3.6,.83,2.9,2.2,.08,.65);

  roomShell(-10.3,8.1,'data','data');
  wallDisplay(-1.5,2.25,-3.52,'ivory',4.3,1.65);
  shelf(3.5,-3.35,'ivory',1.6);
  desk(-3,0,'ivory');desk(-.5,0,'ivory');desk(-3,2.3,'ivory',false);
  box('ivory',2.0,1.36,1.15,2.3,.16,1.4);
  box('cyan',2,1.46,1.15,1.9,.025,1.1);
  for(const xof of [-.85,.85])box('brass',2+xof,.98,1.15,.08,.7,1);
  chair(2,2.35,'blue');
  cyl('glass',3.8,1.7,-.7,.72,1.8);horizontalRing(.74,2.6,'brass',.04,3.8,-.7);
  cyl('lilac',3.8,.88,-.7,.74,.18);sphere('screenLight',3.8,1.75,-.7,.23);
  shelf(1.45,-3.35,'ivory',1.7);
  desk(-.5,2.3,'ivory',false);
  for(let i=0;i<4;i++)box(['blue','lilac','cyan','data'][i],1.35+i*.4,1.64+i*.1,1.1,.22,.25+i*.2,.22);
  box('blue',4.55,1.2,2.25,.45,.85,1.4);plant(4.4,2.95,.6);

  roomShell(10.3,8.1,'slate','oak');
  wallDisplay(-1.55,2.25,-3.52,'screen',3,1.5);
  for(let i=0;i<3;i++){
    box('navy',3.2+i*.55,1.8,-3.2,.45,2.1,.65);
    for(let k=0;k<8;k++)box(k%3?'blue':'cyan',3.2+i*.55,.95+k*.22,-2.85,.3,.055,.025);
  }
  desk(-3,1.7,'wood');desk(-.55,1.7,'wood');
  box('wood',2.9,1.35,.7,3.1,.19,1.45);
  for(const xof of [-1.25,1.25])box('navy',2.9+xof,.96,.7,.1,.76,1.1);
  for(let i=0;i<5;i++)box(['navy','blue','amber','ivory','coral'][i],1.9+i*.45,1.55,.6,.26,.2+(i%3)*.12,.3);
  // Compact original robot arm on the prototyping bench.
  cyl('navy',3.65,1.55,-1.2,.35,.2);cyl('amber',3.65,1.87,-1.2,.14,.6);
  box('amber',3.42,2.2,-1.2,.8,.18,.18,-.3);sphere('slate',3.1,2.2,-1.2,.17);
  box('amber',2.95,2.05,-1.2,.16,.4,.15);box('slate',2.95,1.82,-1.2,.33,.1,.2);
  box('wood',3.45,1.37,-1.3,2.1,.18,1.1);
  box('wood',.65,2.1,-3.5,1.4,1.8,.12);
  for(let i=0;i<6;i++){
    box(i%2?'brass':'ivory',.25+(i%3)*.4,1.65+Math.floor(i/3)*.65,-3.39,.07,.38,.07);
    box('slate',.25+(i%3)*.4,1.82+Math.floor(i/3)*.65,-3.39,.2,.08,.08);
  }
  box('navy',-4.3,1.34,-1.35,.82,1.15,1.6);
  for(let i=0;i<3;i++)box('brass',-4.3,.99+i*.3,-.53,.66,.025,.03);
  cyl('amber',2.45,1.62,.95,.13,.18);box('screen',2.65,1.68,.6,.47,.32,.28);
  box('oak',-.65,.82,-1.4,2.5,.07,1.2);box('ivory',-.65,1.05,-1.4,.6,.45,.5);

  offset.set(0,0,0);zoneScale=1;
  // Observatory HQ is a genuine open dome, not a solid roof hiding the room.
  cyl('navy',0,.38,0,5.35,.85);cyl('ivory',0,.83,0,5.27,.14);cyl('oak',0,.93,0,4.98,.06);
  horizontalRing(5.17,1.04,'brass',.1);horizontalRing(4.95,1.1,'goldLight',.035);
  // A curved inhabited base makes the observatory a headquarters, not a wire cage.
  for(let i=0;i<18;i++){
    const a=i*Math.PI*2/18,x=Math.sin(a)*5.04,z=Math.cos(a)*5.04;
    const back=z<-.3;
    box('ivory',x,back?2.05:1.39,z,1.72,back?2.25:.9,.25,a);
    if(back){
      box('wood',x*.978,2.1,z*.978,1.42,1.85,.08,a);
      box('goldLight',x*.968,3.05,z*.968,1.43,.055,.055,a);
    }else{
      box('glass',x,2.15,z,1.44,.62,.055,a);
      box('brass',x,2.51,z,1.7,.065,.08,a);
    }
  }
  horizontalRing(5.05,3.24,'ivory',.16);horizontalRing(5.07,3.40,'brass',.055);
  horizontalRing(5.01,3.02,'goldLight',.035);
  shelf(-2.7,-3.65,'wood',1.8);shelf(2.7,-3.65,'wood',1.8);
  wallDisplay(0,2.25,-4.83,'screen',2.6,1.45);
  box('terracotta',-3.5,1.35,-.45,1.2,.5,.75);box('terracotta',-3.95,1.75,-.45,.2,.7,.8);
  box('terracotta',3.5,1.35,-.45,1.2,.5,.75);box('terracotta',3.95,1.75,-.45,.2,.7,.8);
  for(let i=0;i<16;i++){
    const a=i*Math.PI*2/16;
    cyl('ivory',Math.sin(a)*5.07,1.75,Math.cos(a)*5.07,.14,1.55);
    if(i>4&&i<12)box('glass',Math.sin(a)*5.03,1.65,Math.cos(a)*5.03,1.7,1.3,.05,a);
  }
  for(let i=0;i<4;i++) {
    const a=i*Math.PI/4,points=[];
    for(let j=0;j<=32;j++) {
      const t=j/32*Math.PI;
      points.push([Math.cos(t)*5.25*Math.cos(a),1.1+Math.sin(t)*5.1,Math.cos(t)*5.25*Math.sin(a)]);
    }
    tube(points,.13,'brass',40);
  }
  horizontalRing(3.56,4.95,'brass',.11);horizontalRing(1.4,6.05,'brass',.12);
  cyl('brass',0,6.19,0,1.45,.1);cyl('goldLight',0,6.26,0,.72,.04);
  cyl('wood',0,1.56,0,2.28,.18);cyl('brass',0,1.2,0,.4,.6);
  cyl('ivory',0,1.67,0,1.6,.04);horizontalRing(1.5,1.72,'goldLight',.055);
  for(let i=0;i<6;i++){
    const a=i*Math.PI*2/6,x=Math.sin(a)*2.9,z=Math.cos(a)*2.9;
    chair(x,z,'terracotta',a,.96);
    if(i%2===0)person(x,z,a,'navy',.96);
  }
  const core = new THREE.Group(); core.position.y=2.65;city.add(core);
  const coreMesh = new THREE.Mesh(new THREE.IcosahedronGeometry(.47,0),materials.goldLight);core.add(coreMesh);
  const coreHalo = new THREE.Mesh(new THREE.TorusGeometry(.85,.022,6,64),materials.goldLight);
  coreHalo.rotation.x=Math.PI/2; core.add(coreHalo);
  cyl('warmGlass',0,3.45,0,.65,3.25);
  for(const a of [Math.PI/4,Math.PI*3/4,Math.PI*5/4,Math.PI*7/4])cyl('goldLight',Math.sin(a)*.65,3.48,Math.cos(a)*.65,.025,3.32);
  horizontalRing(.66,2.1,'goldLight',.035);horizontalRing(.66,4.85,'goldLight',.035);
  tube([[-.95,1,5.18],[-.95,2.2,5.18],[-.65,2.85,5.18],[0,3.08,5.18],[.65,2.85,5.18],[.95,2.2,5.18],[.95,1,5.18]],.18,'ivory',32);
  tube([[-.73,1,5.23],[-.73,2.16,5.23],[-.45,2.66,5.23],[0,2.84,5.23],[.45,2.66,5.23],[.73,2.16,5.23],[.73,1,5.23]],.04,'goldLight',32);
  for(const [x,z]of[[-3.7,-2.4],[3.7,-2.4]])plant(x,z,1.1,false,1);
  // Raised but unobtrusive entrance threshold.
  for(let i=0;i<3;i++)box('ivory',0,.2+i*.19,5.4-i*.3,2.6,.2,1.0);

  // Matching satellite neighborhoods establish how other maps share this world.
  for(const [cx,cz,sz]of[[-32,-22,3.3],[31,-24,3.7],[-30,20,2.5]]) {
    offset.set(cx,-4,cz);
    cyl('navy',0,0,0,sz,.8);cyl('ivory',0,.43,0,sz,.08);
    horizontalRing(sz-.12,.5,'brass',.045);horizontalRing(sz,.0,'cyan',.025);
    box('ivory',0,1.1,0,sz*1.2,1.3,sz*.95);box('glass',0,1.1,sz*.49,sz*.95,.75,.03);
    box('navy',0,1.8,0,sz*1.3,.17,sz*1.06);plant(-sz*.65,sz*.4,.6,false,.4);
    plant(sz*.65,-sz*.4,.6,true,.4);
    add('cone','navy',[0,-1.3,0],[sz*.5,2,sz*.5],[0,0,Math.PI]);
  }
  offset.set(0,0,0);
  // Draw-call reduction: hundreds of furniture/plant parts share geometry and material.
  for(const batch of batches.values()) {
    const mesh = new THREE.InstancedMesh(batch.geometry,batch.material,batch.matrices.length);
    batch.matrices.forEach((matrix,i)=>mesh.setMatrixAt(i,matrix));
    mesh.instanceMatrix.needsUpdate=true;mesh.castShadow=!batch.material.transparent;
    mesh.receiveShadow=true;mesh.frustumCulled=false;city.add(mesh);
  }

  const skyMaterial = new THREE.ShaderMaterial({
    side: THREE.BackSide,depthWrite:false,
    uniforms:{top:{value:new THREE.Color('#030817')},bottom:{value:new THREE.Color('#163a55')},nebula:{value:new THREE.Color('#40345d')}},
    vertexShader:'varying vec3 vP; void main(){vP=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:'varying vec3 vP;uniform vec3 top;uniform vec3 bottom;uniform vec3 nebula;void main(){vec3 n=normalize(vP);float t=smoothstep(-0.4,0.75,n.y);vec3 c=mix(bottom,top,t);float cloud=pow(max(0.0,sin(n.x*8.0+n.z*5.0)*sin(n.z*7.0-n.y*6.0)),6.0);c+=nebula*cloud*0.32;gl_FragColor=vec4(c,1.0);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}'
  });
  const sky=new THREE.Mesh(new THREE.SphereGeometry(330,32,16),skyMaterial);scene.add(sky);
  const starPositions=[];
  let seed=47;
  function random(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;}
  for(let i=0;i<1100;i++){
    const u=random()*2-1,a=random()*Math.PI*2,r=120+random()*100,s=Math.sqrt(1-u*u);
    starPositions.push(r*s*Math.cos(a),r*u,r*s*Math.sin(a));
  }
  const starGeometry=new THREE.BufferGeometry();starGeometry.setAttribute('position',new THREE.Float32BufferAttribute(starPositions,3));
  const stars=new THREE.Points(starGeometry,new THREE.PointsMaterial({color:'#dbe9ff',size:.17,sizeAttenuation:true,transparent:true,opacity:.85,depthWrite:false}));scene.add(stars);
  const planetMaterial=new THREE.ShaderMaterial({
    uniforms:{},vertexShader:'varying vec3 vN;varying vec3 vV;varying vec3 vP;void main(){vP=position;vec4 mv=modelViewMatrix*vec4(position,1.0);vN=normalize(normalMatrix*normal);vV=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}',
    fragmentShader:'varying vec3 vN;varying vec3 vV;varying vec3 vP;void main(){float edge=pow(1.0-max(0.0,dot(normalize(vN),normalize(vV))),3.0);vec3 n=normalize(vP);float clouds=smoothstep(.2,.8,sin(n.x*38.0+n.z*19.0)*sin(n.z*44.0+n.y*31.0));vec3 col=mix(vec3(.035,.09,.17),vec3(.12,.23,.33),clouds*.45);col=mix(col,vec3(.19,.55,.72),edge*.85);gl_FragColor=vec4(col,1.0);}'
  });
  const planet=new THREE.Mesh(new THREE.SphereGeometry(100,64,32),planetMaterial);
  planet.position.set(5,-161,-18);scene.add(planet);
  const atmosphere=new THREE.Mesh(new THREE.SphereGeometry(100.8,64,32),new THREE.MeshBasicMaterial({color:'#66a8d1',transparent:true,opacity:.14,side:THREE.BackSide,depthWrite:false}));atmosphere.position.copy(planet.position);scene.add(atmosphere);

  const pickMeshes=[];
  const pickMaterial=new THREE.MeshBasicMaterial({visible:false});
  for(const [id,center]of Object.entries(centers)){
    const hit=new THREE.Mesh(new THREE.BoxGeometry(id==='hq'?10.5:10.8,id==='hq'?5.3:3.6,id==='hq'?10.5:8.6),pickMaterial);
    hit.position.copy(center);hit.position.y=id==='hq'?3:2;hit.userData.id=id;scene.add(hit);pickMeshes.push(hit);
  }
  const selectedMaterial=new THREE.MeshBasicMaterial({color:'#bceade',transparent:true,opacity:.7,depthWrite:false});
  const selectedRing=new THREE.Mesh(new THREE.TorusGeometry(5.7,.045,6,80),selectedMaterial);selectedRing.rotation.x=-Math.PI/2;selectedRing.position.y=.96;selectedRing.visible=false;scene.add(selectedRing);
  const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
  let pointerStart=null,selected=null,tour=false,world='orbital',quality='balanced',disposed=false,frame=0,lastFrame=0,frames=0,contextLost=false,paused=false;
  let destination=null;
  function pick(event){
    const rect=renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    raycaster.setFromCamera(pointer,camera);return raycaster.intersectObjects(pickMeshes,false)[0]?.object.userData.id||null;
  }
  function pointerDown(event){pointerStart={x:event.clientX,y:event.clientY,time:performance.now()};destination=null;}
  function pointerUp(event){
    if(pointerStart&&Math.hypot(event.clientX-pointerStart.x,event.clientY-pointerStart.y)<5&&performance.now()-pointerStart.time<500){const id=pick(event);if(id){focus(id);onSelect(id);}}
    pointerStart=null;
  }
  function pointerMove(event){if(!pointerStart)renderer.domElement.style.cursor=pick(event)?'pointer':'grab';}
  renderer.domElement.addEventListener('pointerdown',pointerDown);
  renderer.domElement.addEventListener('pointerup',pointerUp);
  renderer.domElement.addEventListener('pointermove',pointerMove);
  function onContextLost(event){event.preventDefault();contextLost=true;container.dispatchEvent(new CustomEvent('space-city-error',{detail:'그래픽 연결이 중단됐습니다. 페이지를 새로 열거나 2D 업무 화면을 이용해 주세요.'}));}
  renderer.domElement.addEventListener('webglcontextlost',onContextLost);
  function focus(id){
    if(!centers[id])return;
    selected=id;tour=false;controls.autoRotate=false;
    const c=centers[id];selectedRing.position.set(c.x,.96,c.z);selectedRing.visible=true;
    selectedRing.scale.setScalar(id==='hq'?1:.93);
    destination={target:new THREE.Vector3(c.x,1.4,c.z),position:new THREE.Vector3(c.x+1,18,c.z+23)};
    if(reducedMotion){camera.position.copy(destination.position);controls.target.copy(destination.target);destination=null;}
  }
  function fittedHomePosition(){
    // Keep the same composition on a narrow viewport instead of cropping the city.
    const scale=Math.max(1,1.28/Math.max(camera.aspect,.3));
    return homePosition.clone().sub(homeTarget).multiplyScalar(scale).add(homeTarget);
  }
  function reset(){
    selected=null;tour=false;controls.autoRotate=false;selectedRing.visible=false;
    destination={target:homeTarget.clone(),position:fittedHomePosition()};
    if(reducedMotion){camera.position.copy(destination.position);controls.target.copy(destination.target);destination=null;}
  }
  function setWorld(id){
    if(!['orbital','cloud','garden','night'].includes(id))return;
    world=id;
    const worlds={
      orbital:['#030817','#163a55','#40345d',1.04,2.9,1.95],
      cloud:['#5a91af','#b0ced0','#e4dcdf',1.15,3.6,2.4],
      garden:['#416d70','#8ca996','#699e72',1.1,3.7,2.55],
      night:['#020411','#0c1835','#303777',.9,1.7,1.5]
    };
    const w=worlds[id];skyMaterial.uniforms.top.value.set(w[0]);skyMaterial.uniforms.bottom.value.set(w[1]);skyMaterial.uniforms.nebula.value.set(w[2]);
    renderer.toneMappingExposure=w[3];sun.intensity=w[4];hemi.intensity=w[5];stars.visible=id==='orbital'||id==='night';planet.visible=id==='orbital'||id==='night';atmosphere.visible=planet.visible;
    materials.goldLight.emissiveIntensity=id==='night'?3:1.8;
  }
  function setTour(enabled){tour=!!enabled;destination=null;controls.autoRotate=tour&&!reducedMotion;controls.autoRotateSpeed=.28;}
  function setQuality(mode){
    quality=['low','balanced','high'].includes(mode)?mode:'balanced';
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,quality==='low'?1:quality==='high'?2:1.5));
    renderer.shadowMap.enabled=quality!=='low';resize();
  }
  let previousAspect=null;
  function resize(){
    const w=Math.max(1,container.clientWidth),h=Math.max(1,container.clientHeight);
    camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);
    if(!selected&&(previousAspect===null||Math.abs(previousAspect-camera.aspect)>.02)){
      if(destination){destination={target:homeTarget.clone(),position:fittedHomePosition()};}
      else {
        const direction=camera.position.clone().sub(controls.target).normalize();
        const distance=fittedHomePosition().distanceTo(homeTarget);
        camera.position.copy(controls.target).addScaledVector(direction,distance);
      }
    }
    previousAspect=camera.aspect;
  }
  const observer=new ResizeObserver(resize);observer.observe(container);resize();
  function animate(time){
    if(disposed)return;frame=requestAnimationFrame(animate);
    if(document.hidden||paused||contextLost||time-lastFrame<1000/(quality==='low'?24:30))return;
    const delta=Math.min((time-lastFrame)/1000,.07);lastFrame=time;
    if(destination){camera.position.lerp(destination.position,.09);controls.target.lerp(destination.target,.09);if(camera.position.distanceTo(destination.position)<.04)destination=null;}
    controls.update(delta);
    if(!reducedMotion){coreMesh.rotation.y=time*.0002;coreHalo.rotation.z=Math.sin(time*.0004)*.12;core.position.y=2.65+Math.sin(time*.001)*.045;}
    renderer.render(scene,camera);frames++;
  }
  function getProjectedAnchors(){
    const w=container.clientWidth,h=container.clientHeight;
    return Object.fromEntries(Object.entries(centers).map(([id,p])=>{const v=p.clone();v.y=id==='hq'?6.7:4.2;v.project(camera);return[id,{x:(v.x*.5+.5)*w,y:(-.5*v.y+.5)*h,visible:v.z>-1&&v.z<1}];}));
  }
  function getMetrics(){return {status:contextLost?'context-lost':'ready',renderer:'Three.js WebGL',version:THREE.REVISION,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,instances:[...batches.values()].reduce((n,b)=>n+b.matrices.length,0),frames,world,quality,selected,tour,camera:camera.position.toArray(),pixelRatio:renderer.getPixelRatio()};}
  function dispose(){
    disposed=true;cancelAnimationFrame(frame);observer.disconnect();controls.dispose();
    renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',pointerUp);renderer.domElement.removeEventListener('pointermove',pointerMove);renderer.domElement.removeEventListener('webglcontextlost',onContextLost);
    const gs=new Set(),ms=new Set();scene.traverse(o=>{if(o.geometry)gs.add(o.geometry);if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>ms.add(m));});
    gs.forEach(g=>g.dispose());ms.forEach(m=>m.dispose());renderer.dispose();renderer.domElement.remove();
  }
  renderer.render(scene,camera);controls.update();frame=requestAnimationFrame(animate);
  queueMicrotask(()=>{if(!disposed)onReady(getMetrics());});
  return {focus,setWorld,setTour,setQuality,reset,dispose,getMetrics,getProjectedAnchors,setPaused(value){paused=!!value;}};
}
