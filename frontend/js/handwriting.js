(function () {
  const state = { profileId: "hefterpro-natur", projectId: null };

  const els = {
    text: $("#text"),
    profile: $("#profile"),
    sheet: $("#sheet"),
    ink: $("#ink"),
    btnRender: $("#btn-render"),
    btnPdf: $("#btn-pdf"),
    btnPng: $("#btn-png"),
    btnJpg: $("#btn-jpg"),
    preview: $("#preview"),
    status: $("#status"),
  };

  (async function init() {
    const profiles = await API.listProfiles();
    els.profile.innerHTML = profiles.map(p =>
      `<option value="${p.id}">${escapeHtml(p.name)}</option>`
    ).join("");
    state.profileId = els.profile.value;
  })();

  els.profile.addEventListener("change", () => { state.profileId = els.profile.value; });

  els.btnRender.addEventListener("click", async () => {
    const text = els.text.value;
    if (!text.trim()) { setStatus(els.status, "Bitte zuerst Text eingeben.", "err"); return; }
    const reset = showSpinner(els.btnRender, "Rendere…");
    setStatus(els.status, "Handschrift wird erzeugt…");
    try {
      const res = await API.render({
        text,
        profile_id: state.profileId,
        sheet_type: els.sheet.value,
        ink_color: els.ink.value,
        jitter: 0.6,
      });
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      setStatus(els.status, `Fertig · ${res.pages} Seite(n).`, "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  function renderPreview(urls) {
    if (!urls.length) {
      els.preview.innerHTML = `<div class="empty-state">Keine Seiten.</div>`;
      return;
    }
    els.preview.innerHTML = urls.map(u =>
      `<div class="page-shadow"><img src="${u}" alt="Vorschau" /></div>`
    ).join("");
  }

  async function exportFormat(fmt) {
    if (!state.projectId) return;
    const btn = { pdf: els.btnPdf, png: els.btnPng, jpg: els.btnJpg }[fmt];
    const reset = showSpinner(btn, fmt.toUpperCase());
    try {
      const res = await API.exportHandwriting(state.projectId, fmt);
      window.open(res.url, "_blank");
      setStatus(els.status, "Export fertig.", "ok");
    } catch (e) {
      setStatus(els.status, "Export fehlgeschlagen: " + e.message, "err");
    } finally { reset(); }
  }

  els.btnPdf.addEventListener("click", () => exportFormat("pdf"));
  els.btnPng.addEventListener("click", () => exportFormat("png"));
  els.btnJpg.addEventListener("click", () => exportFormat("jpg"));
})();
