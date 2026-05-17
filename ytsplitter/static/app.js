/* YouTube Splitter – UI logic */

let jobId = null;
let duration = 0;
let marks = [];
let mode = 'manual';
let chapters = [];
let timeParts = [];
let pollTimer = null;

// ---------------------------------------------------------------- Download --

async function startDownload() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) return;

  setBtn('btn-dl', true, 'Lädt…');
  hide('dl-error');
  show('dl-status');
  hide('player-section');
  hide('parts-section');
  setProgress(5);

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Fehler beim Start');
    jobId = data.job_id;
    startPoll();
  } catch (e) {
    showError(e.message);
  }
}

function startPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      const meta = await res.json();
      handleStatus(meta);
      if (meta.status === 'ready' || meta.status === 'error') clearInterval(pollTimer);
    } catch (_) {}
  }, 1500);
}

function handleStatus(meta) {
  const txt = document.getElementById('status-text');
  const ttl = document.getElementById('status-title');
  if (meta.status === 'downloading') {
    txt.textContent = 'Wird heruntergeladen…';
    ttl.textContent = meta.title || '';
    setProgress(meta.progress || 40);
  } else if (meta.status === 'ready') {
    setProgress(100);
    txt.textContent = '✓ Fertig!';
    ttl.textContent = meta.title || '';
    setBtn('btn-dl', false, 'Herunterladen');
    loadPlayer(meta);
  } else if (meta.status === 'error') {
    showError(meta.error || 'Unbekannter Fehler');
  }
}

function loadPlayer(meta) {
  duration = meta.duration || 0;
  chapters = meta.chapters || [];

  document.getElementById('video-title').textContent = meta.title || 'Video';
  document.getElementById('dur-display').textContent = fmt(duration);

  const vid = document.getElementById('vid');
  vid.src = `/api/jobs/${jobId}/video`;

  if (chapters.length > 0) {
    show('chapters-badge');
    document.getElementById('tab-chapters').disabled = false;
    document.getElementById('tab-chapters').classList.remove('hidden');
    renderChapters();
  }

  marks = [];
  timeParts = [];
  renderMarks();
  updateTimeline();

  show('player-section');
  document.getElementById('player-section').scrollIntoView({ behavior: 'smooth' });
}

// ------------------------------------------------------------------ Player --

document.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === 'm' || e.key === 'M') { e.preventDefault(); addMark(); }
});

document.addEventListener('DOMContentLoaded', () => {
  const vid = document.getElementById('vid');
  vid.addEventListener('timeupdate', () => {
    document.getElementById('cur-time').textContent = fmt(vid.currentTime);
    const pct = duration > 0 ? (vid.currentTime / duration) * 100 : 0;
    document.getElementById('tl-progress').style.width = pct + '%';
  });

  document.getElementById('timeline').addEventListener('click', e => {
    if (!duration) return;
    const r = e.currentTarget.getBoundingClientRect();
    document.getElementById('vid').currentTime = ((e.clientX - r.left) / r.width) * duration;
  });
});

// ------------------------------------------------------------------- Marks --

function addMark() {
  const t = document.getElementById('vid').currentTime;
  if (!jobId) return;
  marks.push({ time: t, name: '' });
  marks.sort((a, b) => a.time - b.time);
  renderMarks();
  updateTimeline();
}

function removeMark(i) {
  marks.splice(i, 1);
  renderMarks();
  updateTimeline();
}

function clearMarks() {
  marks = [];
  renderMarks();
  updateTimeline();
}

function renderMarks() {
  const el = document.getElementById('mark-list');
  if (!marks.length) {
    el.innerHTML = `<p style="font-size:14px;color:var(--muted);padding:12px 0;text-align:center">Noch keine Marken. Drücke <kbd>M</kbd> im Video.</p>`;
    return;
  }
  el.innerHTML = marks.map((m, i) => {
    const end = marks[i + 1] ? marks[i + 1].time : duration;
    return `<div class="mark-item">
      <span class="mark-time">${fmt(m.time)}</span>
      <input type="text" placeholder="Part ${i + 1} Name…" value="${esc(m.name)}" oninput="marks[${i}].name=this.value" />
      <span class="mark-end">→ ${fmt(end)}</span>
      <button class="btn-x" onclick="removeMark(${i})">×</button>
    </div>`;
  }).join('');
}

function updateTimeline() {
  const tl = document.getElementById('timeline');
  tl.querySelectorAll('.timeline-mark').forEach(e => e.remove());
  if (!duration) return;
  marks.forEach((m, i) => {
    const div = document.createElement('div');
    div.className = 'timeline-mark';
    div.style.left = (m.time / duration * 100) + '%';
    div.title = m.name || `Part ${i + 1}`;
    tl.appendChild(div);
  });
}

// --------------------------------------------------------------- Time mode --

function generateTimeMarks() {
  const mins = parseFloat(document.getElementById('interval').value) || 2;
  const sec = mins * 60;
  if (!duration || sec <= 0) return;

  timeParts = [];
  let t = 0, i = 1;
  while (t < duration) {
    const end = Math.min(t + sec, duration);
    timeParts.push({ start: t, end, name: `Part ${i}` });
    t = end; i++;
  }

  document.getElementById('time-mark-list').innerHTML = timeParts.map((p, idx) => `
    <div class="mark-item">
      <span class="mark-time">${fmt(p.start)} – ${fmt(p.end)}</span>
      <input type="text" value="${esc(p.name)}" oninput="timeParts[${idx}].name=this.value" />
    </div>`).join('');
}

// ---------------------------------------------------------- Chapters mode --

function renderChapters() {
  document.getElementById('chapters-list').innerHTML = chapters.map((ch, i) => {
    const end = chapters[i + 1] ? chapters[i + 1].start_time : duration;
    return `<div class="mark-item">
      <span class="mark-time">${fmt(ch.start_time)}</span>
      <span style="flex:1;font-size:14px">${esc(ch.title)}</span>
      <span class="mark-end">→ ${fmt(end)}</span>
    </div>`;
  }).join('');
}

// ----------------------------------------------------------------- Mode tab --

function setMode(m) {
  mode = m;
  ['manual', 'time', 'chapters'].forEach(x => {
    document.getElementById(`mode-${x}`).classList.toggle('hidden', x !== m);
    document.getElementById(`tab-${x}`).classList.toggle('active', x === m);
  });
}

// ------------------------------------------------------------------- Split --

async function doSplit() {
  if (!jobId) return;

  let timestamps = [];
  if (mode === 'manual') {
    if (!marks.length) { alert('Erst Schnittmarken setzen (M-Taste).'); return; }
    timestamps = marks.map((m, i) => ({
      start: m.time,
      end: marks[i + 1] ? marks[i + 1].time : duration,
      name: m.name || `Part ${i + 1}`,
    }));
  } else if (mode === 'time') {
    if (!timeParts.length) { alert('Erst "Vorschau" klicken.'); return; }
    timestamps = timeParts;
  } else if (mode === 'chapters') {
    if (!chapters.length) { alert('Keine Kapitel vorhanden.'); return; }
    timestamps = chapters.map((ch, i) => ({
      start: ch.start_time,
      end: chapters[i + 1] ? chapters[i + 1].start_time : duration,
      name: ch.title,
    }));
  }

  setBtn('btn-split', true, 'Wird geschnitten…');
  document.getElementById('split-status').textContent = 'ffmpeg läuft…';

  try {
    const res = await fetch(`/api/jobs/${jobId}/split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timestamps }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Fehler');
    renderParts(data.parts);
    document.getElementById('split-status').textContent = `${data.parts.length} Parts erstellt ✓`;
  } catch (e) {
    document.getElementById('split-status').textContent = 'Fehler: ' + e.message;
  } finally {
    setBtn('btn-split', false, 'Video aufteilen ✂');
  }
}

function renderParts(parts) {
  document.getElementById('parts-list').innerHTML = parts.map((p, i) => `
    <div class="part-item">
      <div class="part-num">${i + 1}</div>
      <div class="part-info">
        <div class="part-name">${esc(p.name)}</div>
        <div class="part-time">${fmt(p.start)} → ${p.end != null ? fmt(p.end) : '–'}</div>
      </div>
      <a href="/api/jobs/${jobId}/parts/${encodeURIComponent(p.part_id)}/download"
         class="btn btn-soft" download style="flex-shrink:0">Download</a>
    </div>`).join('');

  show('parts-section');
  document.getElementById('parts-section').scrollIntoView({ behavior: 'smooth' });
}

function downloadAll() {
  document.querySelectorAll('#parts-list a[download]').forEach((a, i) => {
    setTimeout(() => a.click(), i * 600);
  });
}

// ----------------------------------------------------------------- Helpers --

function fmt(sec) {
  if (sec == null || sec === '') return '–';
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return `${h}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function setBtn(id, disabled, text) {
  const b = document.getElementById(id);
  if (!b) return;
  b.disabled = disabled;
  b.textContent = text;
}

function setProgress(pct) {
  document.getElementById('progress-fill').style.width = pct + '%';
}

function showError(msg) {
  const el = document.getElementById('dl-error');
  el.textContent = 'Fehler: ' + msg;
  show('dl-error');
  hide('dl-status');
  setBtn('btn-dl', false, 'Herunterladen');
}

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
