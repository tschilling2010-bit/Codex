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

  const els = {};

  function cacheEls() {
    Object.assign(els, {
      viewList: $("#view-list"),
      viewDetail: $("#view-detail"),
      profileGrid: $("#profile-grid"),
      btnNewProfile: $("#btn-new-profile"),
      btnBack: $("#btn-back"),
      btnDelete: $("#btn-delete"),
      profileName: $("#profile-name"),
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
      sSize: $("#s-size"), sSizeVal: $("#s-size-val"),
      sThickness: $("#s-thickness"), sThicknessVal: $("#s-thickness-val"),
      sSheet: $("#s-sheet"),
      sInk: $("#s-ink"),
    });
  }

  (async function init() {
    cacheEls();
    bindUI();
    await loadProfiles();
  })();

  // ---------------- Views ----------------
  function showList() {
    state.activeId = null;
    state.profile = null;
    els.viewList.style.display = "";
    els.viewDetail.style.display = "none";
  }

  function showDetail() {
    els.viewList.style.display = "none";
    els.viewDetail.style.display = "";
  }

  // ---------------- Profile list ----------------
  async function loadProfiles() {
    try {
      state.profiles = await API.listProfiles();
    } catch (e) {
      els.profileGrid.innerHTML = `<p class="muted">Fehler: ${escapeHtml(e.message)}</p>`;
      return;
    }
    renderProfileGrid();
  }

  function renderProfileGrid() {
    if (state.profiles.length === 0) {
      els.profileGrid.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1">
          Noch keine Schriften. Erstelle dein erstes Profil!
        </div>`;
      return;
    }
    els.profileGrid.innerHTML = state.profiles.map(p => {
      const pairs = (p.pairs || []).filter(pr => pr.uploaded_at).length;
      const badge = p.glyph_count > 0
        ? `<span style="color:var(--ok); font-size:13px">${p.glyph_count} Buchstaben</span>`
        : '<span class="muted" style="font-size:13px">Noch keine Vorlagen</span>';
      return `
        <a class="card interactive" data-id="${p.id}" href="#">
          <h3>${escapeHtml(p.name)}</h3>
          <p>${pairs} von ${MAX_PAIRS} Paaren · ${badge}</p>
        </a>`;
    }).join("");

    $$(".card.interactive", els.profileGrid).forEach(card => {
      card.addEventListener("click", (e) => {
        e.preventDefault();
        openProfile(card.dataset.id);
      });
    });
  }

  async function openProfile(id) {
    state.activeId = id;
    state.pairFiles = {};
    state.pairPreviews = {};
    try {
      state.profile = await API.getProfile(id);
    } catch (e) {
      alert("Profil konnte nicht geladen werden: " + e.message);
      return;
    }
    showDetail();
    els.profileName.value = state.profile.name;
    applySettingsToUI(state.profile.settings);
    renderPairs();
    updateRenderButton();
    activateTab("templates");
  }

  // ---------------- Tabs ----------------
  function activateTab(name) {
    $$(".tab-btn", els.viewDetail).forEach(b => b.classList.toggle("active", b.dataset.tab === name));
    $$(".tab-panel", els.viewDetail).forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
  }

  // ---------------- Settings ----------------
  function applySettingsToUI(s) {
    els.sSize.value = s.size_scale;
    els.sSizeVal.textContent = fmtScale(s.size_scale);
    els.sThickness.value = s.thickness;
    els.sThicknessVal.textContent = fmtScale(s.thickness);
    els.sSheet.value = s.sheet_type;
    els.sInk.value = s.ink_color;
  }

  function updateRenderButton() {
    const ok = state.profile && state.profile.glyph_count > 0;
    els.btnRender.disabled = !ok;
    msg(els.status, ok ? "Bereit." : "Lade zuerst Vorlagen im Tab „Vorlagen" hoch.");
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
    bindPairCards();
    els.btnPairAdd.disabled = pairs.length >= MAX_PAIRS;
    els.btnPairAdd.textContent = pairs.length >= MAX_PAIRS ? "Alle 4 Paare vorhanden" : "+ Neues Paar";
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
          <div style="margin-top:12px"><button class="btn btn-soft btn-pair-create">Template erzeugen</button></div>
        </div>`;
    }

    const done = !!pair.uploaded_at;
    const badge = done
      ? `<span style="color:var(--ok); font-size:13px; font-weight:600">${pair.glyph_count} Buchstaben</span>`
      : '<span class="muted" style="font-size:13px">warte auf Upload</span>';
    const pdfUrl = API.pairPdfUrl(state.profile.id, idx);
    const previewUrl = state.pairPreviews[idx]
      || (done ? `/files/templates/${state.profile.id}/pair-${idx}/glyph-preview.png?t=${pair.uploaded_at}` : null);

    return `
      <div class="pair-card card" data-pair="${idx}" style="padding:20px">
        <div style="display:flex; justify-content:space-between; align-items:center">
          <strong>Paar ${num}</strong>
          ${badge}
        </div>
        <div style="margin-top:12px">
          <a href="${pdfUrl}" class="btn btn-ghost" style="padding:8px 16px; font-size:13px" download>PDF herunterladen &amp; ausdrucken</a>
        </div>
        <div class="field-row" style="margin-top:14px">
          <div style="flex:1">
            <label class="field">Seite 1 (Foto/Scan)</label>
            <input type="file" class="pair-page1" accept="image/*" style="font-size:14px" />
          </div>
          <div style="flex:1">
            <label class="field">Seite 2 (Foto/Scan)</label>
            <input type="file" class="pair-page2" accept="image/*" style="font-size:14px" />
          </div>
        </div>
        <div style="margin-top:12px"><button class="btn btn-primary btn-pair-upload" disabled>Buchstaben extrahieren</button></div>
        ${previewUrl ? `
          <div style="margin-top:14px">
            <p class="muted" style="font-size:13px; margin-bottom:6px">Extrahierte Buchstaben:</p>
            <img src="${previewUrl}" alt="Glyphen" style="max-width:100%; border:1px solid var(--border); border-radius:8px" />
          </div>` : ""}
      </div>`;
  }

  function bindPairCards() {
    $$(".pair-card", els.pairsList).forEach(card => {
      const idx = parseInt(card.dataset.pair, 10);
      const btnCreate = $(".btn-pair-create", card);
      if (btnCreate) btnCreate.addEventListener("click", () => onCreatePair(idx, btnCreate));
      const p1 = $(".pair-page1", card);
      const p2 = $(".pair-page2", card);
      if (p1) p1.addEventListener("change", () => onPageSelected(idx, 1, p1.files[0], card));
      if (p2) p2.addEventListener("change", () => onPageSelected(idx, 2, p2.files[0], card));
      const btnUp = $(".btn-pair-upload", card);
      if (btnUp) btnUp.addEventListener("click", () => onUploadPair(idx, btnUp));
    });
  }

  async function onCreatePair(idx, btn) {
    if (!state.activeId) return;
    const reset = showSpinner(btn, "Erzeuge…");
    msg(els.pairStatus, `Paar ${idx + 1} wird erzeugt…`);
    try {
      await API.createPair(state.activeId, idx);
      state.profile = await API.getProfile(state.activeId);
      renderPairs();
      msg(els.pairStatus, `Paar ${idx + 1} erzeugt. PDF herunterladen, ausdrucken, ausfüllen, Fotos hochladen.`, "ok");
    } catch (e) {
      msg(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  function onPageSelected(idx, pageNum, file, card) {
    state.pairFiles[idx] = state.pairFiles[idx] || {};
    state.pairFiles[idx][pageNum] = file || null;
    const btn = $(".btn-pair-upload", card);
    btn.disabled = !(state.pairFiles[idx][1] && state.pairFiles[idx][2]);
  }

  async function onUploadPair(idx, btn) {
    const files = state.pairFiles[idx] || {};
    if (!files[1] || !files[2]) return;
    const reset = showSpinner(btn, "Extrahiere…");
    msg(els.pairStatus, `Paar ${idx + 1}: Buchstaben werden extrahiert…`);
    try {
      const res = await API.uploadPair(state.activeId, idx, files[1], files[2]);
      if (res.preview_url) state.pairPreviews[idx] = res.preview_url + "?t=" + Date.now();
      state.profile = res.profile;
      state.pairFiles[idx] = {};
      renderPairs();
      updateRenderButton();
      msg(els.pairStatus, `Paar ${idx + 1}: ${res.glyph_count} Buchstaben extrahiert!`, "ok");
    } catch (e) {
      msg(els.pairStatus, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  // ---------------- Auto-save ----------------
  const saveName = debounce(async () => {
    const name = els.profileName.value.trim();
    if (!name || !state.activeId) return;
    try {
      state.profile = await API.renameProfile(state.activeId, name);
    } catch (_) {}
  }, 600);

  const saveSettings = debounce(async () => {
    if (!state.activeId) return;
    try {
      state.profile = await API.updateProfileSettings(state.activeId, {
        size_scale: parseFloat(els.sSize.value),
        thickness: parseFloat(els.sThickness.value),
        sheet_type: els.sSheet.value,
        ink_color: els.sInk.value,
      });
    } catch (_) {}
  }, 400);

  // ---------------- Events ----------------
  function bindUI() {
    els.btnNewProfile.addEventListener("click", () => {
      els.newName.value = "";
      if (typeof els.dlgNew.showModal === "function") {
        els.dlgNew.showModal();
        setTimeout(() => els.newName.focus(), 50);
      } else {
        const name = prompt("Name:");
        if (name) createProfile(name);
      }
    });

    els.formNew.addEventListener("submit", async (e) => {
      if (e.submitter && e.submitter.value === "ok") {
        e.preventDefault();
        const name = els.newName.value.trim();
        if (!name) return;
        els.dlgNew.close();
        await createProfile(name);
      }
    });

    els.btnBack.addEventListener("click", async () => {
      await loadProfiles();
      showList();
    });

    els.btnDelete.addEventListener("click", async () => {
      if (!state.activeId) return;
      if (!confirm(`„${state.profile?.name}" wirklich löschen?`)) return;
      try {
        await API.deleteProfile(state.activeId);
      } catch (_) {}
      await loadProfiles();
      showList();
    });

    els.profileName.addEventListener("input", saveName);

    els.sSize.addEventListener("input", () => { els.sSizeVal.textContent = fmtScale(els.sSize.value); saveSettings(); });
    els.sThickness.addEventListener("input", () => { els.sThicknessVal.textContent = fmtScale(els.sThickness.value); saveSettings(); });
    els.sSheet.addEventListener("change", saveSettings);
    els.sInk.addEventListener("change", saveSettings);

    els.btnPairAdd.addEventListener("click", () => {
      if (!state.activeId || !state.profile) return;
      const used = new Set((state.profile.pairs || []).map(p => p.index));
      let free = -1;
      for (let i = 0; i < MAX_PAIRS; i++) { if (!used.has(i)) { free = i; break; } }
      if (free < 0) return;
      onCreatePair(free, els.btnPairAdd);
    });

    $$(".tab-btn", els.viewDetail).forEach(btn => {
      btn.addEventListener("click", () => activateTab(btn.dataset.tab));
    });

    els.btnRender.addEventListener("click", renderText);
    els.btnPdf.addEventListener("click", () => doExport("pdf"));
    els.btnPng.addEventListener("click", () => doExport("png"));
    els.btnJpg.addEventListener("click", () => doExport("jpg"));
  }

  async function createProfile(name) {
    try {
      const p = await API.createProfile(name);
      await loadProfiles();
      openProfile(p.id);
    } catch (e) {
      alert("Fehler: " + e.message);
    }
  }

  // ---------------- Rendering ----------------
  async function renderText() {
    if (!state.activeId) return;
    const text = els.text.value;
    if (!text.trim()) { msg(els.status, "Bitte Text eingeben.", "err"); return; }
    const reset = showSpinner(els.btnRender, "Rendere…");
    msg(els.status, "Handschrift wird erzeugt…");
    try {
      const res = await API.render({ text, profile_id: state.activeId });
      state.projectId = res.project_id;
      renderPreview(res.preview_urls);
      [els.btnPdf, els.btnPng, els.btnJpg].forEach(b => b.disabled = false);
      msg(els.status, `Fertig — ${res.pages} Seite(n).`, "ok");
    } catch (e) {
      msg(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  }

  function renderPreview(urls) {
    els.preview.innerHTML = urls.length
      ? urls.map(u => '<div class="page-shadow"><img src="' + u + '" alt="Vorschau" /></div>').join("")
      : '<div class="empty-state">Keine Seiten.</div>';
  }

  async function doExport(fmt) {
    if (!state.projectId) return;
    const btn = { pdf: els.btnPdf, png: els.btnPng, jpg: els.btnJpg }[fmt];
    const reset = showSpinner(btn, fmt.toUpperCase());
    try {
      const res = await API.exportHandwriting(state.projectId, fmt);
      window.open(res.url, "_blank");
      msg(els.status, "Export fertig.", "ok");
    } catch (e) {
      msg(els.status, "Export: " + e.message, "err");
    } finally { reset(); }
  }

  // ---------------- Utils ----------------
  function msg(el, text, kind) {
    setStatus(el, text, kind);
    if (el) el.style.display = text ? "" : "none";
  }

  function fmtScale(v) {
    return Number(v).toFixed(2).replace(/0$/, "") + "\u00d7";
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
})();
