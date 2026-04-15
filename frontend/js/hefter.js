(function () {
  const state = { uploadId: null, files: [], projectId: null };
  const els = {
    drop: $("#drop"),
    files: $("#files"),
    list: $("#file-list"),
    topic: $("#topic"),
    extra: $("#extra"),
    btnProcess: $("#btn-process"),
    btnPdf: $("#btn-pdf"),
    btnPng: $("#btn-png"),
    btnJpg: $("#btn-jpg"),
    status: $("#status"),
    preview: $("#preview"),
  };

  els.drop.addEventListener("click", () => els.files.click());
  els.drop.addEventListener("dragover", (e) => { e.preventDefault(); els.drop.classList.add("dragover"); });
  els.drop.addEventListener("dragleave", () => els.drop.classList.remove("dragover"));
  els.drop.addEventListener("drop", (e) => {
    e.preventDefault(); els.drop.classList.remove("dragover");
    handleFiles(e.dataTransfer.files);
  });
  els.files.addEventListener("change", () => handleFiles(els.files.files));

  function handleFiles(files) {
    state.files = [...files];
    els.list.innerHTML = state.files.map(f =>
      `<div>• ${escapeHtml(f.name)} <span class="muted">(${fmtBytes(f.size)})</span></div>`
    ).join("");
  }

  els.btnProcess.addEventListener("click", async () => {
    const reset = showSpinner(els.btnProcess, "Erstelle…");
    setStatus(els.status, "Dateien werden analysiert…");
    try {
      let uploadId = "";
      if (state.files.length) {
        const up = await API.hefterUpload(state.files);
        uploadId = up.upload_id;
      }
      const res = await API.hefterProcess({
        upload_id: uploadId,
        additional_text: els.extra.value,
        topic_hint: els.topic.value,
      });
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      setStatus(els.status, `Fertig · ${res.preview_urls.length} Seite(n) · Thema: ${res.document.title}`, "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  function renderPreview(urls) {
    if (!urls.length) { els.preview.innerHTML = `<div class="empty-state">Keine Seiten.</div>`; return; }
    els.preview.innerHTML = urls.map(u =>
      `<div class="page-shadow"><img src="${u}" alt="Vorschau" /></div>`
    ).join("");
  }

  async function exportFormat(fmt) {
    if (!state.projectId) return;
    const btn = { pdf: els.btnPdf, png: els.btnPng, jpg: els.btnJpg }[fmt];
    const reset = showSpinner(btn, fmt.toUpperCase());
    try {
      const res = await API.exportHefter(state.projectId, fmt);
      window.open(res.url, "_blank");
      setStatus(els.status, "Export fertig.", "ok");
    } catch (e) {
      setStatus(els.status, "Export fehlgeschlagen: " + e.message, "err");
    } finally { reset(); }
  }
  els.btnPdf.addEventListener("click", () => exportFormat("pdf"));
  els.btnPng.addEventListener("click", () => exportFormat("png"));
  els.btnJpg.addEventListener("click", () => exportFormat("jpg"));

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
