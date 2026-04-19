(function () {
  const MAX_PAIRS = 4;

  const state = {
    profiles: [],
    activeId: null,
    profile: null,
    projectId: null,
    pairFiles: {},
  };

  const els = {
    profile: $("#profile"),
    btnProfileNew: $("#btn-profile-new"),
    btnProfileDelete: $("#btn-profile-delete"),
    panel: $("#profile-panel"),
    profileName: $("#profile-name"),
    btnProfileRename: $("#btn-profile-rename"),

    sSize: $("#s-size"), sSizeVal: $("#s-size-val"),
    sThickness: $("#s-thickness"), sThicknessVal: $("#s-thickness-val"),
    sSheet: $("#s-sheet"),
    sInk: $("#s-ink"),
    settingsStatus: $("#settings-status"),

    pairsList: $("#pairs-list"),
    btnPairAdd: $("#btn-pair-add"),
    pairStatus: $("#pair-status"),

    dlgNew: $("#dlg-new-profile"),
    formNew: $("#form-new-profile"),
    newName: $("#new-profile-name"),

    text: $("#text"),
    oSize: $("#o-size"), oSizeVal: $("#o-size-val"),
    oThickness: $("#o-thickness"), oThicknessVal: $("#o-thickness-val"),
    btnRender: $("#btn-render"),
    btnResetOverride: $("#btn-reset-override"),
    btnPdf: $("#btn-pdf"),
    btnPng: $("#btn-png"),
    btnJpg: $("#btn-jpg"),
    preview: $("#preview"),
    status: $("#status"),
  };

  const overrides = { size: null, thickness: null };

  (async function init() {
    bindUI();
    await reloadProfiles();
  })();

  // ---------------- Profile list ----------------
  async function reloadProfiles(preferId) {
    try {
      state.profiles = await API.listProfiles();
    } catch (e) {
      setStatus(els.status, "Profile konnten nicht geladen werden: " + e.message, "err");
      return;
    }

    if (state.profiles.length === 0) {
      els.profile.innerHTML = '<option value="">— Kein Profil vorhanden —</option>';
      state.activeId = null;
      state.profile = null;
      els.panel.style.display = "none";
      els.btnRender.disabled = true;
      els.btnProfileDelete.disabled = true;
      setStatus(els.status, 'Kein Profil vorhanden. Klick auf "+ Neues Profil", um loszulegen.', "err");
      return;
    }

    els.profile.innerHTML = state.profiles.map(p =>
      `<option value="${p.id}">${escapeHtml(p.name)} (${p.glyph_count} Glyphen)</option>`
    ).join("");

    const target = preferId && state.profiles.some(p => p.id === preferId)
      ? preferId
      : (state.activeId && state.profiles.some(p => p.id === state.activeId)
        ? state.activeId : state.profiles[0].id);
    els.profile.value = target;
    await activateProfile(target);
  }

  async function activateProfile(id) {
    state.activeId = id;
    state.pairFiles = {};
    try {
      state.profile = await API.getProfile(id);
    } catch (e) {
      setStatus(els.status, "Profil konnte nicht geladen werden: " + e.message, "err");
      return;
    }
    els.panel.style.display = "";
    els.btnProfileDelete.disabled = false;
    els.profileName.value = state.profile.name;
    applySettingsToUI(state.profile.settings);
    renderPairs();
    updateRenderButtonState();
  }

  function applySettingsToUI(s) {
    els.sSize.value = s.size_scale;
    els.sSizeVal.textContent = fmtScale(s.size_scale);
    els.sThickness.value = s.thickness;
    els.sThicknessVal.textContent = fmtScale(s.thickness);
    els.sSheet.value = s.sheet_type;
    els.sInk.value = s.ink_color;
  }

  function updateRenderButtonState() {
    const canRender = state.profile && state.profile.glyph_count > 0;
    els.btnRender.disabled = !canRender;
    if (!canRender) {
      setStatus(els.status, "Profil hat noch keine Glyphen. Fülle mindestens ein Template-Paar aus.", "err");
    } else {
      setStatus(els.status, "Bereit.");
    }
  }

  // ---------------- Pair rendering ----------------
  function renderPairs() {
    const pairs = state.profile.pairs || [];
    const byIndex = new Map(pairs.map(p => [p.index, p]));

    const items = [];
    for (let i = 0; i < MAX_PAIRS; i++) {
      items.push(pairCardHTML(i, byIndex.get(i)));
    }
    els.pairsList.innerHTML = items.join("");

    $$(".pair-card", els.pairsList).forEach(card => {
      const idx = parseInt(card.dataset.pair, 10);
      const btnCreate = $(".btn-pair-create", card);
      const btnUpload = $(".btn-pair-upload", card);
      const inpFiles = $(".pair-files", card);
      const dropZone = $(".pair-drop", card);

      if (btnCreate) {
        btnCreate.addEventListener("click", () => onCreatePair(idx, btnCreate));
      }
      if (inpFiles) {
        inpFiles.addEventListener("change", () => onPairFilesSelected(idx, inpFiles.files, card));
      }
      if (dropZone) {
        dropZone.addEventListener("click", () => inpFiles.click());
        dropZone.addEventListener("dragover", e => {
          e.preventDefault();
          dropZone.classList.add("dragover");
        });
        dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
        dropZone.addEventListener("drop", e => {
          e.preventDefault();
          dropZone.classList.remove("dragover");
          onPairFilesSelected(idx, e.dataTransfer.files, card);
        });
      }
      if (btnUpload) {
        btnUpload.addEventListener("click", () => onUploadPair(idx, btnUpload, card));
      }
    });

    const freeSlots = MAX_PAIRS - pairs.length;
    els.btnPairAdd.disabled = freeSlots <= 0;
    els.btnPairAdd.textContent = freeSlots <= 0
      ? "Alle 4 Paare vorhanden"
      : "+ Neues Template-Paar";
  }

  function pairCardHTML(idx, pair) {
    const num = idx + 1;
    let status = "";
    let body = "";

    if (!pair) {
      status = '<span class="muted">noch nicht erstellt</span>';
      body = `
        <div class="toolbar">
          <button class="btn btn-soft btn-pair-create">Template erzeugen</button>
        </div>`;
    } else if (!pair.uploaded_at) {
      status = '<span class="muted">Template erzeugt — warte auf Upload</span>';
      body = `
        ${pairLinksHTML(pairUrls(idx))}
        ${pairUploadZoneHTML()}
      `;
    } else {
      status = `<span style="color:#2a7">✓ fertig · ${pair.glyph_count} Glyphen</span>`;
      body = `
        ${pairLinksHTML(pairUrls(idx))}
        <details style="margin-top:8px">
          <summary style="cursor:pointer; font-size:14px">Paar neu hochladen (überschreibt)</summary>
          ${pairUploadZoneHTML()}
        </details>
      `;
    }

    return `
      <div class="pair-card" data-pair="${idx}" style="border:1px solid var(--border); border-radius:10px; padding:14px">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px">
          <strong>Paar ${num}</strong>
          ${status}
        </div>
        ${body}
      </div>`;
  }

  function pairUrls(idx) {
    if (!state.profile) return [];
    return [1, 2].map(n =>
      `/files/templates/${state.profile.id}/pair-${idx}/page-${n}.png`
    );
  }

  function pairLinksHTML(urls) {
    return `<div style="font-size:14px">
      Seiten: ${urls.map((u, i) =>
        `<a href="${u}" target="_blank" style="font-weight:600; margin-right:12px">Seite ${i + 1}</a>`
      ).join("")}
    </div>`;
  }

  function pairUploadZoneHTML() {
    return `
      <div class="dropzone pair-drop" style="padding:16px; margin-top:10px">
        <strong>Gescannte Seiten hier ablegen</strong>
        <span class="muted">oder klicken zum Auswählen (2 Bilder)</span>
        <input type="file" class="pair-files" multiple accept="image/*" hidden />
        <div class="file-list pair-file-list"></div>
      </div>
      <div class="toolbar" style="margin-top:10px">
        <button class="btn btn-primary btn-pair-upload" disabled>Buchstaben extrahieren</button>
      </div>`;
  }

  async function onCreatePair(idx, btn) {
    if (!state.activeId) return;
    const reset = showSpinner(btn, "Erzeuge…");
    setStatus(els.pairStatus, `Paar ${idx + 1} wird erzeugt…`);
    try {
      await API.createPair(state.activeId, idx);
      state.profile = await API.getProfile(state.activeId);
      renderPairs();
      setStatus(els.pairStatus, `Paar ${idx + 1} erzeugt. Bitte ausdrucken & ausfüllen.`, "ok");
    } catch (e) {
      setStatus(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  function onPairFilesSelected(idx, files, card) {
    const arr = [...files];
    state.pairFiles[idx] = arr;
    const fileList = $(".pair-file-list", card);
    const btnUpload = $(".btn-pair-upload", card);
    fileList.innerHTML = arr.map(f =>
      `<div>- ${escapeHtml(f.name)} <span class="muted">(${fmtBytes(f.size)})</span></div>`
    ).join("");
    btnUpload.disabled = arr.length === 0;
  }

  async function onUploadPair(idx, btn, _card) {
    const files = state.pairFiles[idx] || [];
    if (!files.length) return;
    const reset = showSpinner(btn, "Extrahiere…");
    setStatus(els.pairStatus, `Paar ${idx + 1}: Buchstaben werden extrahiert…`);
    try {
      const updated = await API.uploadPair(state.activeId, idx, files);
      state.profile = updated;
      state.pairFiles[idx] = [];
      renderPairs();
      await reloadProfiles(state.activeId);
      setStatus(els.pairStatus,
        `Paar ${idx + 1}: fertig. Profil hat jetzt ${updated.glyph_count} Glyphen.`, "ok");
    } catch (e) {
      setStatus(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  // ---------------- Event wiring ----------------
  function bindUI() {
    els.profile.addEventListener("change", async () => {
      await activateProfile(els.profile.value);
    });

    els.btnProfileNew.addEventListener("click", () => {
      els.newName.value = "";
      if (typeof els.dlgNew.showModal === "function") {
        els.dlgNew.showModal();
        setTimeout(() => els.newName.focus(), 50);
      } else {
        const name = prompt("Profilname:");
        if (name) createNewProfile(name);
      }
    });

    els.formNew.addEventListener("submit", async (e) => {
      const action = e.submitter && e.submitter.value;
      if (action === "ok") {
        e.preventDefault();
        const name = els.newName.value.trim();
        if (!name) return;
        els.dlgNew.close();
        await createNewProfile(name);
      }
    });

    els.btnProfileDelete.addEventListener("click", async () => {
      if (!state.activeId) return;
      if (!confirm(`Profil "${state.profile?.name || state.activeId}" wirklich löschen?`)) return;
      try {
        await API.deleteProfile(state.activeId);
        state.activeId = null;
        state.profile = null;
        await reloadProfiles();
      } catch (e) {
        setStatus(els.status, "Fehler: " + e.message, "err");
      }
    });

    els.btnProfileRename.addEventListener("click", async () => {
      const name = els.profileName.value.trim();
      if (!name || !state.activeId) return;
      try {
        state.profile = await API.renameProfile(state.activeId, name);
        setStatus(els.settingsStatus, "Name gespeichert.", "ok");
        await reloadProfiles(state.activeId);
      } catch (e) {
        setStatus(els.settingsStatus, "Fehler: " + e.message, "err");
      }
    });

    const debouncedSave = debounce(saveSettings, 400);

    els.sSize.addEventListener("input", () => {
      els.sSizeVal.textContent = fmtScale(els.sSize.value);
      debouncedSave();
    });
    els.sThickness.addEventListener("input", () => {
      els.sThicknessVal.textContent = fmtScale(els.sThickness.value);
      debouncedSave();
    });
    els.sSheet.addEventListener("change", saveSettings);
    els.sInk.addEventListener("change", saveSettings);

    els.btnPairAdd.addEventListener("click", () => {
      if (!state.activeId || !state.profile) return;
      const used = new Set((state.profile.pairs || []).map(p => p.index));
      let free = -1;
      for (let i = 0; i < MAX_PAIRS; i++) {
        if (!used.has(i)) { free = i; break; }
      }
      if (free < 0) {
        setStatus(els.pairStatus, "Alle 4 Paare sind belegt.", "err");
        return;
      }
      const card = $(`.pair-card[data-pair="${free}"]`, els.pairsList);
      const btn = card ? $(".btn-pair-create", card) : els.btnPairAdd;
      onCreatePair(free, btn || els.btnPairAdd);
    });

    els.oSize.addEventListener("input", () => {
      overrides.size = parseFloat(els.oSize.value);
      els.oSizeVal.textContent = fmtScale(overrides.size);
    });
    els.oThickness.addEventListener("input", () => {
      overrides.thickness = parseFloat(els.oThickness.value);
      els.oThicknessVal.textContent = fmtScale(overrides.thickness);
    });
    els.btnResetOverride.addEventListener("click", () => {
      overrides.size = null;
      overrides.thickness = null;
      if (state.profile) {
        els.oSize.value = state.profile.settings.size_scale;
        els.oThickness.value = state.profile.settings.thickness;
      }
      els.oSizeVal.textContent = "Profil";
      els.oThicknessVal.textContent = "Profil";
    });

    els.btnRender.addEventListener("click", renderText);
    els.btnPdf.addEventListener("click", () => exportFormat("pdf"));
    els.btnPng.addEventListener("click", () => exportFormat("png"));
    els.btnJpg.addEventListener("click", () => exportFormat("jpg"));
  }

  async function createNewProfile(name) {
    try {
      const p = await API.createProfile(name);
      await reloadProfiles(p.id);
      setStatus(els.pairStatus, "Profil erstellt. Erzeuge jetzt dein erstes Template-Paar.", "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    }
  }

  async function saveSettings() {
    if (!state.activeId) return;
    const payload = {
      size_scale: parseFloat(els.sSize.value),
      thickness: parseFloat(els.sThickness.value),
      sheet_type: els.sSheet.value,
      ink_color: els.sInk.value,
    };
    try {
      state.profile = await API.updateProfileSettings(state.activeId, payload);
      setStatus(els.settingsStatus, "Einstellungen gespeichert.", "ok");
      const i = state.profiles.findIndex(p => p.id === state.activeId);
      if (i >= 0) state.profiles[i] = state.profile;
    } catch (e) {
      setStatus(els.settingsStatus, "Fehler: " + e.message, "err");
    }
  }

  // ---------------- Rendering ----------------
  async function renderText() {
    if (!state.activeId) return;
    const text = els.text.value;
    if (!text.trim()) {
      setStatus(els.status, "Bitte zuerst Text eingeben.", "err");
      return;
    }
    const reset = showSpinner(els.btnRender, "Rendere…");
    setStatus(els.status, "Handschrift wird erzeugt…");
    try {
      const payload = { text, profile_id: state.activeId };
      if (overrides.size !== null) payload.size_scale = overrides.size;
      if (overrides.thickness !== null) payload.thickness = overrides.thickness;

      const res = await API.render(payload);
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      setStatus(els.status, `Fertig - ${res.pages} Seite(n).`, "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

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

  // ---------------- Utils ----------------
  function fmtScale(v) {
    return Number(v).toFixed(2).replace(/0$/, "") + "\u00d7";
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }
})();
