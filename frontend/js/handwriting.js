(function () {
  const MAX_PAIRS = 4;

  const state = {
    profiles: [],
    activeId: null,
    profile: null,
    projectId: null,
    pairFiles: {},
    pairPreviews: {},
  };

  const els = {
    profile: $("#profile"),
    btnProfileNew: $("#btn-profile-new"),
    btnProfileDelete: $("#btn-profile-delete"),
    panel: $("#profile-panel"),
    profileName: $("#profile-name"),
    profileNameRow: $("#profile-name-row"),

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
    btnRender: $("#btn-render"),
    btnPdf: $("#btn-pdf"),
    btnPng: $("#btn-png"),
    btnJpg: $("#btn-jpg"),
    preview: $("#preview"),
    status: $("#status"),
  };

  (async function init() {
    bindTabs();
    bindUI();
    await reloadProfiles();
  })();

  // ---------------- Tabs ----------------
  function bindTabs() {
    $$(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        $$(".tab-btn").forEach(b => b.classList.remove("active"));
        $$(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = $("#tab-" + btn.dataset.tab);
        if (panel) panel.classList.add("active");
      });
    });
  }

  // ---------------- Profile list ----------------
  async function reloadProfiles(preferId) {
    try {
      state.profiles = await API.listProfiles();
    } catch (e) {
      showStatus(els.status, "Profile konnten nicht geladen werden: " + e.message, "err");
      return;
    }

    if (state.profiles.length === 0) {
      els.profile.innerHTML = '<option value="">— Kein Profil —</option>';
      state.activeId = null;
      state.profile = null;
      els.panel.style.display = "none";
      els.profileNameRow.style.display = "none";
      els.btnRender.disabled = true;
      els.btnProfileDelete.disabled = true;
      showStatus(els.status, 'Erstelle ein Profil im Tab "Schrift erstellen".', "err");
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
    const switched = state.activeId !== id;
    state.activeId = id;
    state.pairFiles = {};
    if (switched) state.pairPreviews = {};
    try {
      state.profile = await API.getProfile(id);
    } catch (e) {
      showStatus(els.status, "Profil konnte nicht geladen werden: " + e.message, "err");
      return;
    }
    els.panel.style.display = "";
    els.profileNameRow.style.display = "";
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
      showStatus(els.status, 'Noch keine Glyphen. Lade im Tab "Schrift erstellen" ein Template-Paar hoch.', "err");
    } else {
      showStatus(els.status, "Bereit.");
    }
  }

  function showStatus(el, msg, kind) {
    setStatus(el, msg, kind);
    if (el) el.style.display = msg ? "" : "none";
  }

  // ---------------- Pair cards ----------------
  function renderPairs() {
    const pairs = state.profile.pairs || [];
    const byIndex = new Map(pairs.map(p => [p.index, p]));

    const items = [];
    for (let i = 0; i < MAX_PAIRS; i++) {
      if (byIndex.has(i) || i === 0 || byIndex.has(i - 1)) {
        items.push(pairCardHTML(i, byIndex.get(i)));
      }
    }
    els.pairsList.innerHTML = items.join("");

    $$(".pair-card", els.pairsList).forEach(card => {
      const idx = parseInt(card.dataset.pair, 10);

      const btnCreate = $(".btn-pair-create", card);
      if (btnCreate) {
        btnCreate.addEventListener("click", () => onCreatePair(idx, btnCreate));
      }

      const inpPage1 = $(".pair-page1", card);
      const inpPage2 = $(".pair-page2", card);
      if (inpPage1) inpPage1.addEventListener("change", () => onPageSelected(idx, 1, inpPage1.files[0], card));
      if (inpPage2) inpPage2.addEventListener("change", () => onPageSelected(idx, 2, inpPage2.files[0], card));

      const btnUpload = $(".btn-pair-upload", card);
      if (btnUpload) btnUpload.addEventListener("click", () => onUploadPair(idx, btnUpload, card));
    });

    const freeSlots = MAX_PAIRS - pairs.length;
    els.btnPairAdd.disabled = freeSlots <= 0;
    els.btnPairAdd.textContent = freeSlots <= 0 ? "Alle 4 Paare vorhanden" : "+ Neues Paar";
  }

  function pairCardHTML(idx, pair) {
    const num = idx + 1;

    if (!pair) {
      return `
        <div class="pair-card card" data-pair="${idx}" style="padding:20px">
          <div style="display:flex; justify-content:space-between; align-items:center">
            <strong>Paar ${num}</strong>
            <span class="muted" style="font-size:13px">nicht erstellt</span>
          </div>
          <div style="margin-top:12px">
            <button class="btn btn-soft btn-pair-create">Template erzeugen</button>
          </div>
        </div>`;
    }

    const urls = pairUrls(idx);
    const done = !!pair.uploaded_at;
    const badge = done
      ? `<span style="color:var(--ok); font-size:13px; font-weight:600">${pair.glyph_count} Buchstaben</span>`
      : '<span class="muted" style="font-size:13px">warte auf Upload</span>';

    const previewUrl = state.pairPreviews[idx]
      || (done ? `/files/templates/${state.profile.id}/pair-${idx}/glyph-preview.png?t=${pair.uploaded_at}` : null);

    return `
      <div class="pair-card card" data-pair="${idx}" style="padding:20px">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <strong>Paar ${num}</strong>
          ${badge}
        </div>

        <div style="display:flex; gap:10px; margin-top:12px; font-size:14px">
          ${urls.map((u, i) =>
            `<a href="${u}" target="_blank" class="btn btn-ghost" style="padding:8px 16px; font-size:13px">Seite ${i + 1} herunterladen</a>`
          ).join("")}
        </div>

        <div class="field-row" style="margin-top:14px">
          <div style="flex:1">
            <label class="field">Seite 1 hochladen</label>
            <input type="file" class="pair-page1" accept="image/*" style="font-size:14px" />
          </div>
          <div style="flex:1">
            <label class="field">Seite 2 hochladen</label>
            <input type="file" class="pair-page2" accept="image/*" style="font-size:14px" />
          </div>
        </div>

        <div style="margin-top:12px">
          <button class="btn btn-primary btn-pair-upload" disabled>Buchstaben extrahieren</button>
        </div>

        ${previewUrl ? `
          <div style="margin-top:14px">
            <p class="muted" style="font-size:13px; margin-bottom:6px">Extrahierte Buchstaben:</p>
            <img src="${previewUrl}" alt="Glyphen" style="max-width:100%; border:1px solid var(--border); border-radius:8px" />
          </div>` : ""}
      </div>`;
  }

  function pairUrls(idx) {
    if (!state.profile) return [];
    return [1, 2].map(n =>
      `/files/templates/${state.profile.id}/pair-${idx}/page-${n}.png`
    );
  }

  async function onCreatePair(idx, btn) {
    if (!state.activeId) return;
    const reset = showSpinner(btn, "Erzeuge…");
    showStatus(els.pairStatus, `Paar ${idx + 1} wird erzeugt…`);
    try {
      await API.createPair(state.activeId, idx);
      state.profile = await API.getProfile(state.activeId);
      renderPairs();
      showStatus(els.pairStatus, `Paar ${idx + 1} erzeugt. Seiten ausdrucken, ausfüllen, hochladen.`, "ok");
    } catch (e) {
      showStatus(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  function onPageSelected(idx, pageNum, file, card) {
    state.pairFiles[idx] = state.pairFiles[idx] || {};
    state.pairFiles[idx][pageNum] = file || null;
    const btnUpload = $(".btn-pair-upload", card);
    btnUpload.disabled = !(state.pairFiles[idx][1] && state.pairFiles[idx][2]);
  }

  async function onUploadPair(idx, btn, _card) {
    const files = state.pairFiles[idx] || {};
    if (!files[1] || !files[2]) return;
    const reset = showSpinner(btn, "Extrahiere…");
    showStatus(els.pairStatus, `Paar ${idx + 1}: Buchstaben werden extrahiert…`);
    try {
      const res = await API.uploadPair(state.activeId, idx, files[1], files[2]);
      if (res.preview_url) {
        state.pairPreviews[idx] = res.preview_url + "?t=" + Date.now();
      }
      state.profile = res.profile;
      state.pairFiles[idx] = {};
      renderPairs();
      await reloadProfiles(state.activeId);
      showStatus(els.pairStatus,
        `Paar ${idx + 1}: ${res.glyph_count} Buchstaben extrahiert. Du kannst jetzt Text umwandeln!`, "ok");
    } catch (e) {
      showStatus(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  // ---------------- Auto-save ----------------
  const autoSaveName = debounce(async () => {
    const name = els.profileName.value.trim();
    if (!name || !state.activeId) return;
    try {
      state.profile = await API.renameProfile(state.activeId, name);
      showStatus(els.settingsStatus, "Gespeichert.", "ok");
      setTimeout(() => showStatus(els.settingsStatus, ""), 1500);
      await reloadProfiles(state.activeId);
    } catch (_) {}
  }, 600);

  const autoSaveSettings = debounce(async () => {
    if (!state.activeId) return;
    const payload = {
      size_scale: parseFloat(els.sSize.value),
      thickness: parseFloat(els.sThickness.value),
      sheet_type: els.sSheet.value,
      ink_color: els.sInk.value,
    };
    try {
      state.profile = await API.updateProfileSettings(state.activeId, payload);
      showStatus(els.settingsStatus, "Gespeichert.", "ok");
      setTimeout(() => showStatus(els.settingsStatus, ""), 1500);
      const i = state.profiles.findIndex(p => p.id === state.activeId);
      if (i >= 0) state.profiles[i] = state.profile;
    } catch (_) {}
  }, 400);

  // ---------------- Event wiring ----------------
  function bindUI() {
    els.profile.addEventListener("change", () => activateProfile(els.profile.value));

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
      if (!confirm(`Profil "${state.profile?.name || state.activeId}" löschen?`)) return;
      try {
        await API.deleteProfile(state.activeId);
        state.activeId = null;
        state.profile = null;
        await reloadProfiles();
      } catch (e) {
        showStatus(els.status, "Fehler: " + e.message, "err");
      }
    });

    els.profileName.addEventListener("input", autoSaveName);

    els.sSize.addEventListener("input", () => {
      els.sSizeVal.textContent = fmtScale(els.sSize.value);
      autoSaveSettings();
    });
    els.sThickness.addEventListener("input", () => {
      els.sThicknessVal.textContent = fmtScale(els.sThickness.value);
      autoSaveSettings();
    });
    els.sSheet.addEventListener("change", autoSaveSettings);
    els.sInk.addEventListener("change", autoSaveSettings);

    els.btnPairAdd.addEventListener("click", () => {
      if (!state.activeId || !state.profile) return;
      const used = new Set((state.profile.pairs || []).map(p => p.index));
      let free = -1;
      for (let i = 0; i < MAX_PAIRS; i++) {
        if (!used.has(i)) { free = i; break; }
      }
      if (free < 0) {
        showStatus(els.pairStatus, "Alle 4 Paare belegt.", "err");
        return;
      }
      onCreatePair(free, els.btnPairAdd);
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
      showStatus(els.pairStatus, "Profil erstellt. Erzeuge jetzt ein Template-Paar.", "ok");
    } catch (e) {
      showStatus(els.status, "Fehler: " + e.message, "err");
    }
  }

  // ---------------- Rendering ----------------
  async function renderText() {
    if (!state.activeId) return;
    const text = els.text.value;
    if (!text.trim()) {
      showStatus(els.status, "Bitte Text eingeben.", "err");
      return;
    }
    const reset = showSpinner(els.btnRender, "Rendere…");
    showStatus(els.status, "Handschrift wird erzeugt…");
    try {
      const res = await API.render({ text, profile_id: state.activeId });
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      showStatus(els.status, `Fertig — ${res.pages} Seite(n).`, "ok");
    } catch (e) {
      showStatus(els.status, "Fehler: " + e.message, "err");
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
      showStatus(els.status, "Export fertig.", "ok");
    } catch (e) {
      showStatus(els.status, "Export fehlgeschlagen: " + e.message, "err");
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
