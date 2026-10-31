// Native audio: explicit gesture only, default off on every visit.
export function mountMusic(doc = document, fetcher = fetch) {
  const audio = doc.getElementById('world-music');
  const button = doc.getElementById('world-music-toggle');
  const volume = doc.getElementById('world-music-volume');
  const status = doc.getElementById('world-music-status');
  if (!audio || !button || !volume || !status) return;
  let attempt = 0;
  audio.volume = 0.25;
  const stopped = (message = '음악은 꺼져 있습니다. 음악 켜기를 눌러 주세요.') => {
    button.textContent = '음악 켜기';
    button.setAttribute('aria-pressed', 'false');
    status.textContent = message;
  };
  const pause = () => { attempt += 1; audio.pause(); stopped(); };
  volume.addEventListener('input', () => {
    const value = Number(volume.value);
    audio.volume = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.25;
  });
  audio.addEventListener('pause', () => stopped());
  audio.addEventListener('error', () => {
    attempt += 1;
    audio.pause();
    stopped('음악을 재생하지 못했습니다. 잠시 후 다시 눌러 주세요.');
  });
  button.addEventListener('click', () => {
    if (button.getAttribute('aria-pressed') === 'true') { pause(); return; }
    const current = ++attempt;
    if (!audio.getAttribute('src')) audio.src = '/api/world/music/audio';
    // Call play immediately inside the gesture, before any network await.
    button.setAttribute('aria-pressed', 'true');
    button.textContent = '음악 끄기';
    status.textContent = '음악을 불러오고 있습니다.';
    Promise.resolve(audio.play()).then(() => {
      if (current !== attempt) return;
      status.textContent = 'Titan · Scott Buckley 재생 중';
    }).catch(() => {
      if (current !== attempt) return;
      stopped('재생을 시작하지 못했습니다. 음악 켜기를 다시 눌러 주세요.');
    });
  });
  doc.addEventListener('visibilitychange', () => { if (doc.hidden) pause(); });
  doc.defaultView?.addEventListener('pagehide', pause);
  fetcher('/api/world/music/status', { credentials: 'same-origin', cache: 'no-store' })
    .then(response => { if (!response.ok) throw new Error('unavailable'); return response.json(); })
    .then(data => {
      button.disabled = data.available !== true;
      stopped(data.available === true ? undefined : '배경음악이 아직 준비되지 않았습니다.');
    }).catch(() => stopped('음악 연결을 확인하지 못했습니다. 새로고침 후 다시 확인해 주세요.'));
}
if (typeof document !== 'undefined') mountMusic();
