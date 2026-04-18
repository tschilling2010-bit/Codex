(function () {
  const state = { profileId: null, projectId: null, templateProfileId: null, templateFiles: [] };

  const els = {
    text: $("#text"),
    profile: $("#profile"),
    sheet: $("#sheet"),
    ink: $("#ink"),
    size: $("#size"),
    sizeVal: $("#size-val"),
    thickness: $("#thickness"),
    thicknessVal: $("#thickness-val"),
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

  (async function init() {
    await loadProfiles();
  })();

  async function loadProfiles(preferred) {
    const profiles = await API.listProfiles();
    if (profiles.length === 0) {
      els.profile.innerHTML = '<option value="">— Kein Profil vorhanden —</option>';
      els.btnRender.disabled = true;
      setStatus(els.status, "Bitte erstelle zuerst ein Handschrift-Profil (unten).", "err");
    } else {
      els.profile.innerHTML = profiles.map(p =>
        `<option value="${p.id}">${escapeHtml(p.name)}</option>`
      ).join("");
      if (preferred && profiles.some(p => p.id === preferred)) {
        els.profile.value = preferred;
      }
      els.btnRender.disabled = false;
    }
    state.profileId = els.profile.value || null;
  }

  els.profile.addEventListener("change", () => { state.profileId = els.profile.value || null; });

  function fmtSlider(v) { return Number(v).toFixed(2).replace(/0$/, "") + "\u00d7"; }
  els.size.addEventListener("input", () => { els.sizeVal.textContent = fmtSlider(els.size.value); });
  els.thickness.addEventListener("input", () => { els.thicknessVal.textContent = fmtSlider(els.thickness.value); });

  // ---------- Rendering ----------
  els.btnRender.addEventListener("click", async () => {
    if (!state.profileId) {
      setStatus(els.status, "Bitte erstelle zuerst ein Handschrift-Profil (unten).", "err");
      return;
    }
    const text = els.text.value;
    if (!text.trim()) { setStatus(els.status, "Bitte zuerst Text eingeben.", "err"); return; }
    const reset = showSpinner(els.btnRender, "Rendere...");
    setStatus(els.status, "Handschrift wird erzeugt...");
    try {
      const res = await API.render({
        text,
        profile_id: state.profileId,
        sheet_type: els.sheet.value,
        ink_color: els.ink.value,
        jitter: 0.6,
        size_scale: parseFloat(els.size.value),
        thickness: parseFloat(els.thickness.value),
      });
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      setStatus(els.status, `Fertig - ${res.pages} Seite(n).`, "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  function renderPreview(urls) {
    if (!urls.length) {
      els.preview.innerHTML = '<div class="empty-state">Keine Seiten.</div>';
      return;
    }
    els.preview.innerHTML = urls.map(u =>
      '<div class="page-shadow"><img src="' + u + '" alt="Vorschau" /></div>'
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
    const reset = showSpinner(els.btnMakeTemplate, "Erzeuge...");
    try {
      const res = await API.createTemplate(els.profileName.value.trim());
      state.templateProfileId = res.profile_id;

      const links = res.page_urls.map((url, i) =>
        '<a href="' + url + '" target="_blank" style="font-weight:600">Seite ' + (i + 1) + '</a>'
      ).join(" &middot; ");

      els.templateInfo.innerHTML =
        'Template fuer <strong>' + escapeHtml(res.name) + '</strong> erzeugt (' + res.pages + ' Seiten, ' + res.cells + ' Zeichen).<br>' +
        'Download: ' + links + '<br>' +
        '<span style="font-size:13px">Jede Seite herunterladen, ausdrucken und ausfuellen.</span>';

      els.btnUploadTemplate.disabled = state.templateFiles.length === 0;
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
      '<div>- ' + escapeHtml(f.name) + ' <span class="muted">(' + fmtBytes(f.size) + ')</span></div>'
    ).join("");
    els.btnUploadTemplate.disabled = !state.templateProfileId || state.templateFiles.length === 0;
  }

  els.btnUploadTemplate.addEventListener("click", async () => {
    if (!state.templateProfileId || !state.templateFiles.length) return;
    const reset = showSpinner(els.btnUploadTemplate, "Extrahiere Buchstaben...");
    setStatus(els.templateStatus, "Buchstaben werden extrahiert...");
    try {
      const name = els.profileName.value.trim() || "Eigene Handschrift";
      const res = await API.uploadTemplate(state.templateProfileId, name, state.templateFiles);
      if (res.glyph_count === 0) {
        setStatus(els.templateStatus, "Keine Buchstaben erkannt. Bitte deutlicher schreiben und erneut scannen.", "err");
      } else {
        setStatus(els.templateStatus,
          "Profil erstellt! " + res.glyph_count + " Buchstaben extrahiert.", "ok");
        await loadProfiles(state.templateProfileId);
      }
    } catch (e) {
      setStatus(els.templateStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });
})();
