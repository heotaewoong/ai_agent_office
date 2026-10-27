(function(){
const D = window.PLAYBOOK;
const $ = s => document.querySelector(s);
const el = (t, a, ...c) => { const e = document.createElement(t); if (a) for (const [k, v] of Object.entries(a)) { if (v == null || v === false) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? '' : v); } for (const x of c.flat()) { if (x == null || x === false) continue; e.append(x instanceof Node ? x : document.createTextNode(String(x))); } return e; };
const A = (href, text, cls) => el('a', {href, target:'_blank', rel:'noopener noreferrer', class:cls}, text);
const dep = id => el('span', {class:'dep', title:D.deptNames[id] || id}, id);
const FIT = {now:'우선 연결', cmp:'먼저 비교', ref:'참고', hold:'보류', out:'제외'};
const DEC = {'우선 재사용':'d1','조건부 검토':'d2','보류':'d3','참고만':'d4'};
const badge = (cls, text) => el('span', {class:'bd ' + cls}, text);

/* TOC */
const secs = [...document.querySelectorAll('main section[id]')];
secs.forEach((s, i) => {
  const n = String(i + 1).padStart(2, '0');
  $('#toc').append(el('li', null, el('a', {href:'#' + s.id, 'data-s':s.id}, el('span', {class:'n'}, n), s.dataset.t)));
  $('#mnav').append(el('a', {href:'#' + s.id, 'data-s':s.id}, s.dataset.t));
});
const links = [...document.querySelectorAll('[data-s]')];
if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(es => { es.forEach(e => { if (e.isIntersecting) { links.forEach(l => l.classList.toggle('on', l.dataset.s === e.target.id)); const m = document.querySelector('#mnav a.on'); if (m && m.scrollIntoView) { const p = m.parentElement; p.scrollLeft = m.offsetLeft - 16; } } }); }, {rootMargin:'-20% 0px -70% 0px'});
  secs.forEach(s => io.observe(s));
}

/* §03 TOP3 */
D.top3.forEach(t => $('#top3').append(el('article', {class:'card'},
  el('span', {class:'rank'}, String(t.rank).padStart(2, '0')), el('h4', null, t.title), el('p', null, t.why),
  el('p', null, el('b', null, '가져올 부분 · '), t.take), el('p', {class:'lim'}, t.limit), A(t.url, '실제 코드·자료 열기 ↗', 'go'))));

/* §04 learning */
D.highlights.forEach(h => $('#highlights').append(el('div', {class:'card'}, el('span', {class:'mono', style:'color:var(--accent)'}, h.label + ' · ' + h.target), el('h4', null, h.title), el('p', null, h.text))));
const stages = []; D.nx.forEach(n => { if (!stages.includes(n.p)) stages.push(n.p); });
const stageOrder = ['첫 기반','첫 사용자 가치','콘텐츠 첫 실험','영상 품질 우선','영상·보고서 공통','운영 연결 전','운영 데이터가 생긴 뒤','반복 업무가 검증된 뒤','전체 부서 확장','문서·매출 연결','지식 재사용','매출 실험','반복 작업 절감','개인 시간 절감','개발 시간 절감'];
stages.sort((a, b) => (stageOrder.indexOf(a) + 99) % 199 - (stageOrder.indexOf(b) + 99) % 199);
let nxStage = '';
const nxChip = (label, val) => el('button', {class:'chip', type:'button', 'aria-pressed': String(nxStage === val), onclick:() => { nxStage = val; renderNx(); }}, label, el('span', {class:'c'}, String(val ? D.nx.filter(n => n.p === val).length : D.nx.length)));
function renderNx(){
  $('#nx-stages').replaceChildren(nxChip('전체', ''), ...stages.map(s => nxChip(s, s)));
  const rows = D.nx.filter(n => !nxStage || n.p === nxStage).sort((a, b) => stages.indexOf(a.p) - stages.indexOf(b.p));
  $('#nx-list').replaceChildren(...rows.map(n => el('details', {class:'x'},
    el('summary', null, el('div', null, el('span', {class:'meta'}, n.id + ' · ' + n.p), el('span', {class:'tt'}, n.n)), el('span', {class:'r'}, ...n.dep.slice(0, 4).map(dep))),
    el('div', {class:'body'}, el('p', null, el('b', null, '가치 · '), n.v), el('p', null, el('b', null, '바뀌는 점 · '), n.delta),
      el('ol', null, ...n.steps.map(s => el('li', null, s))), el('dl', {class:'kv'}, el('dt', null, '받는 결과'), el('dd', null, n.art), el('dt', null, '담당'), el('dd', null, n.dep.map(d => d + ' ' + (D.deptNames[d] || '')).join(' · ')), el('dt', null, '근거 소스'), el('dd', null, n.src.join(' · ')), n.files ? el('dt', null, '제안 파일') : null, n.files ? el('dd', {class:'mono'}, n.files) : null)))));
}
renderNx();
$('#sources9').replaceChildren(...D.sources.map(s => el('details', {class:'x'},
  el('summary', null, el('div', null, el('span', {class:'meta'}, s.id + ' · ' + s.a), el('span', {class:'tt'}, s.t)), el('span', {class:'r'})),
  el('div', {class:'body'}, el('p', null, el('b', null, '읽은 범위 · '), s.r), el('p', null, el('b', null, '읽지 않은 것 · '), s.x), el('div', {class:'links'}, A(s.u, '원문 열기 ↗'))))));
D.yt.forEach((s, i) => $('#yt').append(el('li', null, el('span', {class:'sn'}, 'STEP ' + (i + 1)), el('b', null, s[0]), el('span', null, s[1]))));
/* features */
const depSel = $('#ft-dep'), srcSel = $('#ft-src');
depSel.append(el('option', {value:''}, '전체 18부서'), ...D.depts.map(d => el('option', {value:d.id}, d.id + ' ' + d.n)));
srcSel.append(el('option', {value:''}, '모든 출처'), ...D.sources.map(s => el('option', {value:s.id}, s.id + ' ' + s.t)));
let ftLimit = 20;
function renderFt(){
  const q = $('#ft-q').value.trim().toLowerCase(), dv = depSel.value, sv = srcSel.value;
  const rows = D.feat.filter(f => (!dv || f.dep.includes(dv)) && (!sv || f.src.includes(sv)) && (!q || (f.n + f.a + f.i + f.o + f.acc).toLowerCase().includes(q)));
  $('#ft-count').textContent = rows.length + ' / ' + D.feat.length + '행';
  $('#ft-list').replaceChildren(...(rows.length ? rows.slice(0, ftLimit).map(f => el('details', {class:'x'},
    el('summary', null, el('div', null, el('span', {class:'meta'}, f.id + ' · ' + f.src.join(',') + (f.cap.length ? ' → ' + f.cap.join(',') : '')), el('span', {class:'tt'}, f.n)), el('span', {class:'r'}, ...f.dep.slice(0, 3).map(dep))),
    el('div', {class:'body'}, el('p', null, f.a), el('dl', {class:'kv'}, el('dt', null, '입력'), el('dd', null, f.i), el('dt', null, '결과'), el('dd', null, f.o), el('dt', null, '통과 검사'), el('dd', null, f.acc))))) : [el('p', {class:'empty'}, '조건에 맞는 기능이 없습니다. 검색어나 필터를 바꿔 보세요.')]));
  $('#ft-more').hidden = rows.length <= ftLimit;
}
['#ft-q','#ft-dep','#ft-src'].forEach(s => $(s).addEventListener(s === '#ft-q' ? 'input' : 'change', () => { ftLimit = 20; renderFt(); }));
$('#ft-more').addEventListener('click', () => { ftLimit += 20; renderFt(); });
renderFt();
$('#refgroups').replaceChildren(...D.refgroups.map(g => el('details', {class:'x'},
  el('summary', null, el('div', null, el('span', {class:'tt'}, g.t)), el('span', {class:'r'}, el('span', {class:'count'}, g.items.length + '개'))),
  el('div', {class:'body'}, el('ul', {style:'margin:0;padding-left:18px;display:grid;gap:4px'}, ...g.items.map(i => el('li', null, i.u ? A(i.u, i.t) : i.t, i.s ? el('span', {style:'color:var(--ink3);font-size:13px'}, ' · ' + i.s) : null)))))));

/* §05 flows */
D.flows.forEach(f => $('#flow-list').append(el('div', {class:'flow'},
  el('div', null, el('span', {class:'fid'}, f.id), el('h4', null, f.title)),
  el('div', null, el('div', {class:'track'}, ...f.steps.flatMap((s, i) => i ? [el('i', null, '→'), el('span', null, s)] : [el('span', null, s)])), el('p', {class:'res'}, '받을 결과 · ' + f.result + ' · 계약 ' + f.ids.join(', '))))));
$('#ideas tbody').append(...D.ideas.map(i => el('tr', null, el('td', {class:'id'}, i.id), el('td', null, i.t), el('td', null, i.reuse === 'now' ? badge('now', '토요일 우선') : i.reuse === 'later' ? badge('ref', '주력 통과 후') : el('span', {class:'sub'}, (i.phase || i.reuse || '').slice(0, 40))), el('td', null, ...i.dep.slice(0, 5).map(d => dep(d.slice(0, 3)))))));

/* §06 depts */
D.depts.forEach(d => $('#dept-grid').append(el('div', {class:'dcard'},
  el('div', {class:'top'}, el('span', {class:'mono'}, d.id), el('small', null, d.of)), el('h4', null, d.n), el('p', null, d.work), el('p', {class:'first'}, '첫 납품 · ' + d.first))));

/* §07 teams */
$('#our-teams tbody').append(...D.ourTeams.map(t => el('tr', null, el('td', null, el('b', null, t.n)), el('td', null, dep(t.lead), el('span', {style:'color:var(--ink3)'}, ' → '), ...t.with_.map(dep)), el('td', null, t.first), el('td', null, t.proof))));
D.patterns.forEach(p => $('#patterns').append(el('div', {class:'card'}, el('h4', null, p.n), el('p', null, p.d), el('p', null, el('b', null, '쓸 때 · '), p.when), el('p', {class:'lim'}, p.ex))));
$('#teams5 tbody').append(...D.teams5.map(t => el('tr', null, el('td', {class:'id'}, t.r), el('td', null, A(t.u, t.n)), el('td', null, t.s), el('td', null, t.f), el('td', null, t.v))));

/* §08 pipelines */
$('#pipes tbody').append(...D.pipelines.map(p => el('tr', null, el('td', {class:'id'}, p.r), el('td', null, p.p), el('td', null, el('span', {class:'sub', style:'color:var(--ink2)'}, p.ref)), el('td', null, p.v))));
$('#obsidian tbody').append(...D.obsidian.map(o => el('tr', null, el('td', null, el('b', null, o[0])), el('td', null, o[1]), el('td', null, o[2]))));


/* content agent v6 */
const AG = D.agent;
$('#ag-stages tbody').append(...AG.stages.map(r => el('tr', null, el('td', {class:'id'}, r[0]), el('td', null, el('b', null, r[1])), el('td', null, r[2]), el('td', null, r[3] === '-' ? el('span', {class:'sub'}, '-') : badge(/[⓪①②③]/.test(r[3]) ? 'hold' : 'ref', r[3])), el('td', null, el('span', {class:'sub', style:'color:var(--ink2)'}, r[4])))));
$('#ag-gates tbody').append(...AG.gates.map(r => el('tr', null, el('td', null, el('b', null, r[0])), el('td', null, r[1]), el('td', null, r[2]), el('td', null, r[3]))));
$('#ag-costs tbody').append(...AG.costs.map(r => el('tr', null, el('td', null, el('b', null, r[0])), el('td', null, r[1]), el('td', null, r[2]), el('td', null, r[3]))));
[['채택', 'now', AG.adopt], ['먼저 비교', 'cmp', AG.compare], ['쓰지 않음', 'out', AG.exclude]].forEach(([t, c, items]) => $('#ag-tools').append(el('div', {class:'card'}, el('h4', null, badge(c, t)), el('ul', {style:'margin:0;padding-left:18px;display:grid;gap:4px;font-size:14px;color:var(--ink2)'}, ...items.map(i => el('li', null, i))))));
AG.priorities.forEach(p => $('#ag-pri').append(el('li', null, el('span', {class:'sn'}, p[0] + ' · ' + p[1]), el('b', null, p[2]), el('span', {class:'gate'}, '완료 · ' + p[3]))));
AG.policies.forEach(t => $('#ag-policy').append(el('li', null, t)));
/* §09 oss */
const catName = Object.fromEntries(D.ossCats);
let osCat = '';
function renderOs(){
  const q = $('#os-q').value.trim().toLowerCase(), fv = $('#os-fit').value, onlyNew = $('#os-new').checked;
  const base = D.oss.filter(o => (!fv || o.f === fv) && (!onlyNew || !o.k) && (!q || (o.n + o.r + o.d + o.t + o.w).toLowerCase().includes(q)));
  const chip = (label, val, n) => el('button', {class:'chip', type:'button', 'aria-pressed': String(osCat === val), onclick:() => { osCat = val; renderOs(); }}, label, el('span', {class:'c'}, String(n)));
  $('#os-cats').replaceChildren(chip('전체', '', base.length), ...D.ossCats.map(([k, v]) => chip(v, k, base.filter(o => o.c === k).length)));
  const rows = base.filter(o => !osCat || o.c === osCat);
  $('#os-count').textContent = rows.length + ' / ' + D.oss.length + '개';
  const order = {now:0, cmp:1, ref:2, hold:3};
  const groups = D.ossCats.map(([k, v]) => [k, v, rows.filter(o => o.c === k).sort((a, b) => order[a.f] - order[b.f])]).filter(g => g[2].length);
  $('#os-list').replaceChildren(...(groups.length ? groups.map(([k, v, items]) => el('div', {class:'ocat'}, el('h4', null, v, el('span', {class:'count'}, items.length + '개')),
    el('div', {class:'list'}, ...items.map(o => el('div', {class:'orow'},
      el('div', {class:'nm'}, A('https://github.com/' + o.r, o.n), el('span', {class:'mono'}, o.r)),
      el('div', {class:'ds'}, o.d, el('span', {class:'w'}, '쓸 부분 · ' + o.t + (o.w ? ' · 주의: ' + o.w : ''))),
      el('div', {class:'bg'}, badge(o.f, FIT[o.f]), o.k ? badge('cat', '1,921 포함') : badge('cat', '새로 찾음'))))))) : [el('p', {class:'empty'}, '조건에 맞는 프로젝트가 없습니다. 필터를 줄여 보세요.')]));
}
['#os-q','#os-fit','#os-new'].forEach(s => $(s).addEventListener(s === '#os-q' ? 'input' : 'change', renderOs));
renderOs();

/* §10 bench */
const mx = Math.max(...D.bench.cats.map(c => c[1]));
D.bench.cats.forEach(([n, v]) => $('#bars').append(el('div', {class:'bar'}, el('span', null, n), el('div', {class:'tr'}, el('div', {class:'fl', style:'width:' + (v / mx * 100).toFixed(1) + '%'})), el('span', {class:'v'}, v.toLocaleString('ko-KR')))));
$('#core8 tbody').append(...D.bench.core.map(c => el('tr', null, el('td', null, A(c.u, c.n), el('div', {style:'margin-top:4px'}, badge(c.f, FIT[c.f]))), el('td', null, c.s), el('td', null, c.d))));
$('#videos').replaceChildren(...D.bench.videos.map((v, i) => el('div', {class:'orow', style:'grid-template-columns:minmax(0,1fr) auto'}, el('div', {class:'nm'}, A(v.u, (i + 1) + '. ' + v.t), el('span', {class:'mono'}, v.ch)), el('div', {class:'bg'}, badge('cat', v.c)))));

/* §11 fields */
function renderFd(){
  const q = $('#fd-q').value.trim().toLowerCase();
  const rows = D.fields.filter(f => !q || (f.id + f.name + f.top.map(t => t.name).join(' ')).toLowerCase().includes(q));
  $('#fd-count').textContent = rows.length + ' / 29분야';
  $('#fd tbody').replaceChildren(...rows.map(f => el('tr', null, el('td', null, el('span', {class:'mono', style:'color:var(--ink3)'}, f.id + ' '), f.name), el('td', {class:'num'}, f.count), ...[0, 1, 2].map(i => el('td', null, f.top[i] ? A(f.top[i].url, f.top[i].name) : '-')))));
}
$('#fd-q').addEventListener('input', renderFd); renderFd();

/* §12 kits */
function renderKt(){
  const q = $('#kt-q').value.trim().toLowerCase(), pf = $('#kt-pf').value, dc = $('#kt-dec').value;
  const rows = D.entries.filter(e => (!pf || e.pf === pf) && (!dc || e.dec === dc) && (!q || (e.t + e.reuse + e.why + e.id).toLowerCase().includes(q)));
  $('#kt-count').textContent = rows.length + ' / ' + D.entries.length + '개';
  $('#kt-list').replaceChildren(...(rows.length ? rows.map(e => el('details', {class:'x'},
    el('summary', null, el('div', null, el('span', {class:'meta'}, e.pf + ' · ' + e.acc + ' · ' + e.id), el('span', {class:'tt'}, e.t)), el('span', {class:'r'}, badge(DEC[e.dec] || 'ref', e.dec))),
    el('div', {class:'body'}, el('p', null, el('b', null, '판단 이유 · '), e.why), el('p', null, el('b', null, '쓸 부분 · '), e.reuse),
      el('ol', null, ...e.lim.map(l => el('li', null, l))),
      el('div', {class:'links'}, A(e.u, '강의·영상·자료실 ↗'), ...e.code.map((u, i) => A(u, '코드·자료 ' + (i + 1) + ' ↗')), e.lic ? badge('cat', '허가 본문 확인') : null)))) : [el('p', {class:'empty'}, '조건에 맞는 후보가 없습니다.')]));
}
['#kt-q','#kt-pf','#kt-dec'].forEach(s => $(s).addEventListener(s === '#kt-q' ? 'input' : 'change', renderKt));
renderKt();

/* §13 roadmap */
D.phases.forEach(p => $('#phases').append(el('li', null, el('span', {class:'sn'}, 'PHASE ' + p.n + ' · ' + p.when), el('b', null, p.t), el('span', null, p.scope), el('span', {class:'gate'}, '통과 · ' + p.gate))));
D.fails.forEach(f => $('#fails').append(el('li', null, f)));
$('#risks tbody').append(...D.risks.map(r => el('tr', null, el('td', null, el('b', null, r[0])), el('td', null, r[1]), el('td', null, r[2]))));

/* §14 sources */
D.dbDocs.forEach(d => $('#dbdocs').append(el('li', null, d.replace(/\.md$/, '').replace(/_/g, ' '))));

let printState = null;
window.addEventListener('beforeprint', () => { printState = [...document.querySelectorAll('details')].map(d => [d, d.open]); printState.forEach(([d]) => { d.open = true; }); ftLimit = 1000; renderFt(); });
window.addEventListener('afterprint', () => { (printState || []).forEach(([d, o]) => { d.open = o; }); printState = null; ftLimit = 20; renderFt(); });
$('#print').addEventListener('click', () => window.print());
if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) setTimeout(() => t.scrollIntoView(), 60); }
})();
