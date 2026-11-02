export function fitPanelSize(width, height, maxWidth, maxHeight, minHeight) {
  return {
    width: Math.min(maxWidth, Math.max(Math.min(320, maxWidth), width)),
    height: Math.min(maxHeight, Math.max(Math.min(minHeight, maxHeight), height)),
  };
}

export function initPanelResize(panel) {
  const handle = panel?.querySelector('.panel-resize');
  if (!handle) return;
  let size = null, drag = null, moved = false;
  const limits = () => ({
    width: Math.max(1, innerWidth - 32),
    height: Math.max(1, innerHeight - (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--world-header-bottom')) || 74) - 24),
    minimum: panel.querySelector('.panel-head').getBoundingClientRect().height + panel.querySelector('.panel-foot').getBoundingClientRect().height + 80,
  });
  const apply = (width, height) => {
    const max = limits();
    size = fitPanelSize(width, height, max.width, max.height, max.minimum);
    panel.style.setProperty('--panel-width', `${size.width}px`);
    panel.style.setProperty('--panel-height', `${size.height}px`);
    panel.classList.add('user-sized');
  };
  const reset = () => {
    size = null; panel.classList.remove('user-sized');
    panel.style.removeProperty('--panel-width'); panel.style.removeProperty('--panel-height');
  };
  handle.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault(); event.stopPropagation(); handle.focus({ preventScroll: true });
    const rect = panel.getBoundingClientRect();
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, width: rect.width, height: rect.height };
    moved = false; handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = drag.x - event.clientX, dy = drag.y - event.clientY;
    moved ||= Math.abs(dx) + Math.abs(dy) > 3;
    if (moved) apply(drag.width + dx, drag.height + dy);
  });
  const release = event => {
    if (!drag || drag.id !== event.pointerId) return;
    if (event.type === 'pointercancel') moved = true;
    drag = null;
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  };
  handle.addEventListener('pointerup', release); handle.addEventListener('pointercancel', release);
  handle.addEventListener('lostpointercapture', () => { drag = null; });
  handle.addEventListener('click', event => {
    event.stopPropagation();
    if (moved) { moved = false; return; }
    const max = limits();
    if (size?.width === max.width && size?.height === max.height) reset(); else apply(max.width, max.height);
  });
  handle.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') moved = false;
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    if (event.key === 'Home') { reset(); return; }
    const rect = panel.getBoundingClientRect(), step = event.shiftKey ? 64 : 24;
    apply(rect.width + (event.key === 'ArrowLeft' ? step : event.key === 'ArrowRight' ? -step : 0),
      rect.height + (event.key === 'ArrowUp' ? step : event.key === 'ArrowDown' ? -step : 0));
  });
  window.addEventListener('resize', () => { if (size) requestAnimationFrame(() => { if (size) apply(size.width, size.height); }); });
}

if (typeof document !== 'undefined') initPanelResize(document.getElementById('panel'));
