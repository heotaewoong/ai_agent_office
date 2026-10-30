// Original HeoBrain UI: reuse existing game controls and their saved state.
export function installPlayHub(doc = document, office = () => window.__officeWorld) {
  const toolbar = doc.querySelector('.world-actions');
  const groups = [
    { id: 'drive', title: '무료 시승', nodes: [doc.querySelector('.free-drive')] },
    { id: 'explore', title: '도시 탐험', nodes: [doc.querySelector('#explore'), doc.querySelector('.city-activities')] },
    { id: 'capture', title: '포획·보유차', nodes: [doc.querySelector('.alien-game')] },
  ];
  if (!toolbar || groups.some(group => group.nodes.some(node => !node))) return null;
  const trigger = doc.createElement('button');
  trigger.type = 'button'; trigger.id = 'btn-play-hub'; trigger.className = 'world-toolbar-btn';
  trigger.textContent = '탐험·무료시승';
  trigger.setAttribute('aria-controls', 'play-hub'); trigger.setAttribute('aria-expanded', 'false');
  const hub = doc.createElement('aside');
  hub.id = 'play-hub'; hub.className = 'play-hub'; hub.hidden = true;
  hub.setAttribute('role', 'dialog'); hub.setAttribute('aria-labelledby', 'play-hub-title');
  hub.innerHTML = '<div class="play-hub-heading"><div><h2 id="play-hub-title">잠깐, 도시로 나가볼까요?</h2><p>업무 화면은 그대로 · 놀이 기록도 그대로</p></div><button type="button" class="play-hub-close" aria-label="탐험·무료시승 닫기">닫기</button></div><div class="play-hub-tabs" role="group" aria-label="놀이 선택"></div><p class="play-hub-note">차량은 포획 없이 무료로 시승할 수 있어요. 보유차 등록은 게임 크레딧만 사용합니다.</p>';
  let selected = 'drive', opened = false;
  const tabs = hub.querySelector('.play-hub-tabs');
  for (const group of groups) {
    const tab = doc.createElement('button'); tab.type = 'button'; tab.textContent = group.title;
    tab.dataset.playSection = group.id; tab.setAttribute('aria-controls', 'play-section-' + group.id);
    const section = doc.createElement('section'); section.id = 'play-section-' + group.id;
    section.setAttribute('aria-label', group.title);
    section.append(...group.nodes); group.section = section; group.tab = tab;
    tab.addEventListener('click', () => select(group.id)); tabs.append(tab); hub.append(section);
  }
  function select(id) {
    selected = id;
    for (const group of groups) {
      const active = group.id === selected;
      group.section.hidden = !active; group.tab.setAttribute('aria-pressed', String(active));
      for (const node of group.nodes) if (node.tagName === 'DETAILS') node.open = opened && active;
    }
  }
  function setOpen(value, restoreFocus = false) {
    opened = value;
    if (value) {
      for (const id of ['btn-build', 'btn-roster', 'btn-results']) {
        const button = doc.getElementById(id);
        if (button?.getAttribute('aria-pressed') === 'true') button.click();
      }
      const panel = doc.getElementById('panel');
      if (panel && !panel.hidden) doc.getElementById('panel-close')?.click();
      const tools = doc.getElementById('world-tools'); if (tools) tools.open = false;
    } else {
      const closeCapture = hub.querySelector('.alien-game-close');
      if (!hub.querySelector('.alien-game-panel')?.hidden) closeCapture?.click();
    }
    const current = office();
    if (current) {
      current.space.playHubOpen = value; current.controls.keys.clear(); current.controls.dragging = false;
    }
    hub.hidden = !value; trigger.setAttribute('aria-expanded', String(value));
    doc.body.classList.toggle('play-hub-open', value); select(selected);
    if (value) groups.find(group => group.id === selected).tab.focus();
    else if (restoreFocus) trigger.focus();
  }
  trigger.addEventListener('click', () => setOpen(!opened, opened));
  hub.querySelector('.play-hub-close').addEventListener('click', () => setOpen(false, true));
  doc.addEventListener('keydown', event => {
    if (!opened || event.key !== 'Escape') return;
    event.preventDefault(); event.stopPropagation(); setOpen(false, true);
  }, true);
  toolbar.addEventListener('click', event => {
    if (opened && event.target.closest('button,summary') && !event.target.closest('#btn-play-hub')) setOpen(false);
  }, true);
  doc.addEventListener('click', event => {
    if (opened && event.target.closest('.free-drive-ride,.tour-start,.alien-game-start') &&
        office()?.space.view === 'walk') {
      setOpen(false);
      // Escape returns to the menu; starting gameplay returns keys to the world.
      const canvas = doc.getElementById('scene');
      if (canvas) { canvas.tabIndex = 0; canvas.focus({ preventScroll: true }); }
    }
  });
  const tools = doc.getElementById('world-tools');
  tools?.addEventListener('toggle', () => { if (opened && tools.open) setOpen(false); });
  // Keep the entry within the first mobile toolbar screen, in DOM reading order.
  doc.body.append(hub); toolbar.insertBefore(trigger, doc.getElementById('btn-attention'));
  doc.body.classList.add('play-hub-ready'); select(selected);
  return { open: () => setOpen(true), close: () => setOpen(false), trigger, hub };
}

if (typeof document !== 'undefined') installPlayHub();
