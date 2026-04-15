(function () {
  const state = {
    profileId: "default",
    projectId: null,
    templateProfileId: null,
    templateFiles: [],
    settings: null,
  };

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
    profileName: $("#profile-name"),
    btnMakeTemplate: $("#btn-make-template"),
    templateInfo: $("#template-info"),
    templateDrop: $("#template-drop"),
    templateFiles: $("#template-files"),
    templateList: $("#template-list"),
    btnUploadTemplate: $("#btn-upload-template"),
    templateStatus: $("#template-status"),
  };

  // ---------- Setup ----------
  (async function init() {
    try {
      const settings = await API.getSettings();
      state.settings = settings;
      els.sheet.value = settings.default_sheet_type;
      els.ink.value = settings.ink_color;
    } catch (_) { /* ignore */ }
    await loadProfiles(state.settings?.default_profile_id);
  })();

  async function loadProfiles(preferred) {
    const profiles = await API.listProfiles();
    els.profile.innerHTML = profiles.map(p =>
      `<option value="${p.id}">${p.name} ${p.source === "default" ? "· Standard" : ""}</option>`
    ).join("");
    if (preferred && profiles.some(p => p.id === preferred)) {
      els.profile.value = preferred;
    }
    state.profileId = els.profile.value;
  }

  els.profile.addEventListener("change", () => { state.profileId = els.profile.value; });

  // ---------- Rendern ----------
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
        margin_mm: state.settings?.margin_mm ?? 20,
        line_height_mm: state.settings?.line_height_mm ?? 9,
        glyph_height_mm: state.settings?.glyph_height_mm ?? 5.5,
        jitter: 1.0,
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
      els.preview.innerHTML = `<div class="empty-state">Keine Seiten.</div>`; return;
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

  // ---------- Template erzeugen ----------
  els.btnMakeTemplate.addEventListener("click", async () => {
    const reset = showSpinner(els.btnMakeTemplate, "Erzeuge…");
    try {
      const res = await API.createTemplate(els.profileName.value.trim());
      state.templateProfileId = res.profile_id;
      els.templateInfo.innerHTML =
        `Template für <strong>${escapeHtml(res.name)}</strong> erzeugt. ` +
        `<a href="${res.template_url}" target="_blank">Template herunterladen</a>. ` +
        `Zeichen-Raster: ${res.meta.pages} Seite(n), ${res.meta.cells.length} Zellen.`;
      els.btnUploadTemplate.disabled = state.templateFiles.length === 0;
      await loadProfiles(state.profileId);
    } catch (e) {
      setStatus(els.templateStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  // ---------- Template Upload ----------
  els.templateDrop.addEventListener("click", () => els.templateFiles.click());
  els.templateDrop.addEventListener("dragover", (e) => { e.preventDefault(); els.templateDrop.classList.add("dragover"); });
  els.templateDrop.addEventListener("dragleave", () => els.templateDrop.classList.remove("dragover"));
  els.templateDrop.addEventListener("drop", (e) => {
    e.preventDefault(); els.templateDrop.classList.remove("dragover");
    handleTemplateFiles(e.dataTransfer.files);
  });
  els.templateFiles.addEventListener("change", () => handleTemplateFiles(els.templateFiles.files));

  function handleTemplateFiles(files) {
    state.templateFiles = [...files];
    els.templateList.innerHTML = state.templateFiles.map(f =>
      `<div>• ${escapeHtml(f.name)} <span class="muted">(${fmtBytes(f.size)})</span></div>`
    ).join("");
    els.btnUploadTemplate.disabled = !state.templateProfileId || state.templateFiles.length === 0;
  }

  els.btnUploadTemplate.addEventListener("click", async () => {
    if (!state.templateProfileId || !state.templateFiles.length) return;
    const reset = showSpinner(els.btnUploadTemplate, "Verarbeite…");
    setStatus(els.templateStatus, "Template wird analysiert…");
    try {
      const res = await API.uploadTemplate(state.templateProfileId, state.templateFiles);
      setStatus(els.templateStatus, `Profil erstellt · ${res.glyph_count} Glyphen.`, "ok");
      await loadProfiles(state.templateProfileId);
    } catch (e) {
      setStatus(els.templateStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
