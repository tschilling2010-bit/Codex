/* YouTube Splitter – frontend logic */

let currentJobId = null;
let videoDuration = 0;
let marks = [];           // [{time, name}] for manual mode
let currentMode = 'manual';
let videoChapters = [];
let pollTimer = null;

// ---------------------------------------------------------------- Download ---

async function startDownload() {
  const url = document.getElementById('yt-url').value.trim();
  if (!url) return;

  setBtnState('btn-download', true, 'Wird geladen…');
  document.getElementById('download-error').classList.add('hidden');
  document.getElementById('download-status').classList.remove('hidden');
  document.getElementById('player-section').style.display = 'none';
  document.getElementById('parts-section').style.display = 'none';
  setProgress(5);

  try {
    const res = await fetch('/api/youtube/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Download fehlgeschlagen');
    }
    const data = await res.json();
    currentJobId = data.job_id;
    pollStatus();
  } catch (e) {
    showDownloadError(e.message);
  }
}

function pollStatus() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!currentJobId) return;
    try {
      const res = await fetch(`/api/youtube/jobs/${currentJobId}`);
      const meta = await res.json();
      updateStatusUI(meta);
      if (meta.status === 'ready' || meta.status === 'error') {
        clearInterval(pollTimer);
      }
    } catch (_) {}
  }, 1500);
}

function updateStatusUI(meta) {
  const statusText = document.getElementById('status-text');
  const statusTitle = document.getElementById('status-title');

  if (meta.status === 'downloading') {
    statusText.textContent = 'Wird heruntergeladen…';
    statusTitle.textContent = meta.title || '';
    setProgress(meta.progress || 40);
  } else if (meta.status === 'ready') {
    setProgress(100);
    statusText.textContent = 'Fertig!';
    statusTitle.textContent = meta.title || '';
    setBtnState('btn-download', false, 'Herunterladen');
    loadVideo(meta);
  } else if (meta.status === 'error') {
    showDownloadError(meta.error || 'Unbekannter Fehler');
  }
}

function loadVideo(meta) {
  videoDuration = meta.duration || 0;
  videoChapters = meta.chapters || [];

  document.getElementById('video-title').textContent = meta.title || 'Video';
  document.getElementById('duration-display').textContent = fmtTime(videoDuration);

  const video = document.getElementById('video-player');
  video.src = `/api/youtube/jobs/${currentJobId}/video`;

  // Show chapters badge
  if (videoChapters.length > 0) {
    document.getElementById('chapters-badge').classList.remove('hidden');
    renderChaptersList();
  } else {
    document.getElementById('chapters-badge').classList.add('hidden');
    document.getElementById('tab-chapters').disabled = true;
    document.getElementById('tab-chapters').style.opacity = '0.4';
  }

  marks = [];
  renderMarkList();
  updateTimeline();

  document.getElementById('player-section').style.display = 'block';

  // scroll to player
  document.getElementById('player-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ------------------------------------------------------------------ Player ---

const video = () => document.getElementById('video-player');

document.addEventListener('keydown', (e) => {
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;

  if (e.key === 'm' || e.key === 'M') {
    e.preventDefault();
    addMarkAtCurrentTime();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const vid = document.getElementById('video-player');

  vid.addEventListener('timeupdate', () => {
    const t = vid.currentTime;
    document.getElementById('current-time-display').textContent = fmtTime(t);
    const pct = videoDuration > 0 ? (t / videoDuration) * 100 : 0;
    document.getElementById('timeline-progress').style.width = pct + '%';
  });

  // Timeline click to seek
  document.getElementById('yt-timeline').addEventListener('click', (e) => {
    if (!videoDuration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    vid.currentTime = pct * videoDuration;
  });
});

// ------------------------------------------------------------------- Marks ---

function addMarkAtCurrentTime() {
  const t = video().currentTime;
  if (!currentJobId) return;
  marks.push({ time: t, name: '' });
  marks.sort((a, b) => a.time - b.time);
  renderMarkList();
  updateTimeline();
}

function removeMark(index) {
  marks.splice(index, 1);
  renderMarkList();
  updateTimeline();
}

function clearMarks() {
  marks = [];
  renderMarkList();
  updateTimeline();
}

function renderMarkList() {
  const container = document.getElementById('mark-list');
  if (marks.length === 0) {
    container.innerHTML = `<p style="font-size:14px; color:var(--text-muted); text-align:center; padding:16px 0">
      Noch keine Marken gesetzt. Drücke <span class="kbd">M</span> während des Videos.
    </p>`;
    return;
  }

  // Build parts preview: mark[i].time → mark[i+1].time (or end)
  container.innerHTML = marks.map((mark, i) => {
    const end = marks[i + 1] ? marks[i + 1].time : videoDuration;
    return `<div class="mark-item">
      <span class="mark-time">${fmtTime(mark.time)}</span>
      <input
        type="text"
        placeholder="Part ${i + 1} Name…"
        value="${escHtml(mark.name)}"
        oninput="marks[${i}].name = this.value"
      />
      <span style="font-size:12px; color:var(--text-muted); min-width:60px; text-align:right">
        → ${fmtTime(end)}
      </span>
      <button class="btn-icon" onclick="removeMark(${i})" title="Entfernen">×</button>
    </div>`;
  }).join('');
}

function updateTimeline() {
  const timeline = document.getElementById('yt-timeline');
  // Remove old mark elements
  timeline.querySelectorAll('.yt-timeline-mark').forEach(el => el.remove());

  if (!videoDuration) return;
  marks.forEach((mark, i) => {
    const pct = (mark.time / videoDuration) * 100;
    const el = document.createElement('div');
    el.className = 'yt-timeline-mark';
    el.style.left = pct + '%';
    el.dataset.label = mark.name || `P${i + 1}`;
    timeline.appendChild(el);
  });
}

// ---------------------------------------------------------- Time-based mode --

function generateTimeMarks() {
  const intervalMin = parseFloat(document.getElementById('time-interval').value) || 2;
  const intervalSec = intervalMin * 60;
  if (!videoDuration || intervalSec <= 0) return;

  const list = document.getElementById('time-mark-list');
  const parts = [];
  let t = 0;
  let i = 1;
  while (t < videoDuration) {
    const end = Math.min(t + intervalSec, videoDuration);
    parts.push({ start: t, end, name: `Part ${i}` });
    t = end;
    i++;
  }

  list.innerHTML = parts.map((p, idx) => `
    <div class="mark-item">
      <span class="mark-time">${fmtTime(p.start)} – ${fmtTime(p.end)}</span>
      <input
        type="text"
        placeholder="${escHtml(p.name)}"
        value="${escHtml(p.name)}"
        data-part-idx="${idx}"
        oninput="updateTimePartName(${idx}, this.value)"
      />
    </div>
  `).join('');

  // Store time parts on window for split
  window._timeParts = parts;
}

function updateTimePartName(idx, val) {
  if (window._timeParts && window._timeParts[idx]) {
    window._timeParts[idx].name = val;
  }
}

// ------------------------------------------------------------ Chapters mode --

function renderChaptersList() {
  const list = document.getElementById('chapters-list');
  if (videoChapters.length === 0) {
    document.getElementById('chapters-available').classList.add('hidden');
    document.getElementById('chapters-unavailable').classList.remove('hidden');
    return;
  }
  document.getElementById('chapters-available').classList.remove('hidden');
  document.getElementById('chapters-unavailable').classList.add('hidden');

  list.innerHTML = videoChapters.map((ch, i) => {
    const end = videoChapters[i + 1] ? videoChapters[i + 1].start_time : videoDuration;
    return `<div class="mark-item">
      <span class="mark-time">${fmtTime(ch.start_time)}</span>
      <span style="flex:1; font-size:14px">${escHtml(ch.title)}</span>
      <span style="font-size:12px; color:var(--text-muted)">→ ${fmtTime(end)}</span>
    </div>`;
  }).join('');
}

// --------------------------------------------------------------- Mode tabs ---

function setMode(mode) {
  currentMode = mode;
  ['manual', 'time', 'chapters'].forEach(m => {
    document.getElementById(`mode-${m}`).classList.toggle('hidden', m !== mode);
    document.getElementById(`tab-${m}`).classList.toggle('active', m === mode);
  });
}

// -------------------------------------------------------------------- Split --

async function doSplit() {
  if (!currentJobId) return;

  let timestamps = [];

  if (currentMode === 'manual') {
    if (marks.length === 0) {
      alert('Bitte zuerst Schnittmarken setzen (M-Taste).');
      return;
    }
    timestamps = marks.map((mark, i) => ({
      start: mark.time,
      end: marks[i + 1] ? marks[i + 1].time : videoDuration,
      name: mark.name || `Part ${i + 1}`,
    }));
  } else if (currentMode === 'time') {
    const parts = window._timeParts;
    if (!parts || parts.length === 0) {
      alert('Bitte zuerst "Vorschau generieren" klicken.');
      return;
    }
    timestamps = parts;
  } else if (currentMode === 'chapters') {
    if (videoChapters.length === 0) {
      alert('Keine Kapitel vorhanden.');
      return;
    }
    timestamps = videoChapters.map((ch, i) => ({
      start: ch.start_time,
      end: videoChapters[i + 1] ? videoChapters[i + 1].start_time : videoDuration,
      name: ch.title,
    }));
  }

  setBtnState('btn-split', true, 'Wird geschnitten…');
  document.getElementById('split-status').textContent = 'ffmpeg läuft…';

  try {
    const res = await fetch(`/api/youtube/jobs/${currentJobId}/split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timestamps }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Split fehlgeschlagen');
    }
    const data = await res.json();
    renderParts(data.parts);
    document.getElementById('split-status').textContent = `${data.parts.length} Parts erstellt ✓`;
  } catch (e) {
    document.getElementById('split-status').textContent = 'Fehler: ' + e.message;
  } finally {
    setBtnState('btn-split', false, 'Video aufteilen');
  }
}

function renderParts(parts) {
  const section = document.getElementById('parts-section');
  const list = document.getElementById('parts-list');

  list.innerHTML = parts.map((part, i) => {
    const startStr = fmtTime(part.start);
    const endStr = part.end != null ? fmtTime(part.end) : '–';
    return `<div class="part-item">
      <div class="part-num">${i + 1}</div>
      <div class="part-info">
        <div class="part-name">${escHtml(part.name)}</div>
        <div class="part-time">${startStr} → ${endStr}</div>
      </div>
      <a
        href="/api/youtube/jobs/${currentJobId}/parts/${encodeURIComponent(part.part_id)}/download"
        class="btn btn-soft"
        download
        style="flex-shrink:0"
      >
        Download
      </a>
    </div>`;
  }).join('');

  section.style.display = 'block';
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function downloadAllParts() {
  document.querySelectorAll('#parts-list a[download]').forEach((a, i) => {
    setTimeout(() => a.click(), i * 600);
  });
}

// ------------------------------------------------------------------ Helpers --

function fmtTime(sec) {
  if (!sec && sec !== 0) return '–';
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}

function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setBtnState(id, disabled, text) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.disabled = disabled;
  btn.textContent = text;
  btn.style.opacity = disabled ? '0.6' : '1';
}

function setProgress(pct) {
  document.getElementById('progress-bar').style.width = pct + '%';
}

function showDownloadError(msg) {
  document.getElementById('download-error').textContent = 'Fehler: ' + msg;
  document.getElementById('download-error').classList.remove('hidden');
  document.getElementById('download-status').classList.add('hidden');
  setBtnState('btn-download', false, 'Herunterladen');
}
