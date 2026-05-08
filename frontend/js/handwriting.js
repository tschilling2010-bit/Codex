(function () {
  "use strict";
  var MAX_PAIRS = 4;
  var state = { profiles: [], activeId: null, profile: null, projectId: null, pairFiles: {}, pairPreviews: {} };

  function getEl(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function on(el, evt, fn) { if (el) el.addEventListener(evt, fn); }

  // ---- Init ----
  document.addEventListener("DOMContentLoaded", function () {
    try { bindUI(); } catch (e) { console.error("bindUI error:", e); }
    loadProfiles().catch(function (e) { console.error("loadProfiles error:", e); });
  });

  // ---- Views ----
  function showList() {
    state.activeId = null;
    state.profile = null;
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "";
    if (vd) vd.style.display = "none";
    hideNewProfileForm();
  }
  function showDetail() {
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "none";
    if (vd) vd.style.display = "";
  }

  // ---- Profiles ----
  function loadProfiles() {
    var grid = getEl("profile-grid");
    return API.listProfiles().then(function (list) {
      state.profiles = list;
      renderProfileGrid();
    }).catch(function (e) {
      if (grid) grid.innerHTML = '<p class="muted">Fehler beim Laden: ' + escapeHtml(e.message) + "</p>";
    });
  }

  function renderProfileGrid() {
    var grid = getEl("profile-grid");
    if (!grid) return;
    if (state.profiles.length === 0) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Noch keine Schriften. Erstelle dein erstes Profil!</div>';
      return;
    }
    grid.innerHTML = state.profiles.map(function (p) {
      var pairs = (p.pairs || []).filter(function (pr) { return pr.uploaded_at; }).length;
      var badge = p.glyph_count > 0
        ? '<span style="color:var(--ok);font-size:13px">' + p.glyph_count + " Buchstaben</span>"
        : '<span class="muted" style="font-size:13px">Noch keine Vorlagen</span>';
      return '<a class="card interactive" data-id="' + p.id + '" href="#">' +
        "<h3>" + escapeHtml(p.name) + "</h3>" +
        "<p>" + pairs + " von " + MAX_PAIRS + " Paaren &middot; " + badge + "</p></a>";
    }).join("");

    qa(".card.interactive", grid).forEach(function (card) {
      card.addEventListener("click", function (e) {
        e.preventDefault();
        openProfile(card.getAttribute("data-id"));
      });
    });
  }

  function openProfile(id) {
    state.activeId = id;
    state.pairFiles = {};
    state.pairPreviews = {};
    return API.getProfile(id).then(function (p) {
      state.profile = p;
      showDetail();
      var nameEl = getEl("profile-name");
      if (nameEl) nameEl.value = p.name;
      applySettingsToUI(p.settings);
      renderPairs();
      updateRenderButton();
      activateTab("templates");
    }).catch(function (e) {
      alert("Profil konnte nicht geladen werden: " + e.message);
    });
  }

  // ---- Tabs ----
  function activateTab(name) {
    var detail = getEl("view-detail");
    if (!detail) return;
    qa(".tab-btn", detail).forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === name);
    });
    qa(".tab-panel", detail).forEach(function (p) {
      p.classList.toggle("active", p.id === "tab-" + name);
    });
  }

  // ---- Settings ----
  function applySettingsToUI(s) {
    var sz = getEl("s-size"), sv = getEl("s-size-val");
    var th = getEl("s-thickness"), tv = getEl("s-thickness-val");
    var sh = getEl("s-sheet"), ink = getEl("s-ink");
    if (sz) sz.value = s.size_scale;
    if (sv) sv.textContent = fmtScale(s.size_scale);
    if (th) th.value = s.thickness;
    if (tv) tv.textContent = fmtScale(s.thickness);
    if (sh) sh.value = s.sheet_type;
    if (ink) ink.value = s.ink_color;
  }

  function updateRenderButton() {
    var ok = state.profile && state.profile.glyph_count > 0;
    var btn = getEl("btn-render");
    var st = getEl("status");
    if (btn) btn.disabled = !ok;
    msg(st, ok ? "Bereit." : 'Lade zuerst Vorlagen im Tab "Vorlagen" hoch.');
  }

  // ---- Pairs ----
  function renderPairs() {
    var list = getEl("pairs-list");
    var addBtn = getEl("btn-pair-add");
    if (!list || !state.profile) return;
    var pairs = state.profile.pairs || [];
    var byIndex = {};
    pairs.forEach(function (p) { byIndex[p.index] = p; });
    var html = [];
    for (var i = 0; i < MAX_PAIRS; i++) {
      if (byIndex[i] || i === 0 || byIndex[i - 1]) {
        html.push(pairCardHTML(i, byIndex[i]));
      }
    }
    list.innerHTML = html.join("");
    bindPairCards(list);
    if (addBtn) {
      addBtn.disabled = pairs.length >= MAX_PAIRS;
      addBtn.textContent = pairs.length >= MAX_PAIRS ? "Alle 4 Paare vorhanden" : "+ Neues Paar";
    }
  }

  function pairCardHTML(idx, pair) {
    var num = idx + 1;
    if (!pair) {
      return '<div class="pair-card card" data-pair="' + idx + '" style="padding:20px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center">' +
        "<strong>Paar " + num + "</strong>" +
        '<span class="muted" style="font-size:13px">nicht erstellt</span></div>' +
        '<div style="margin-top:12px"><button class="btn btn-soft btn-pair-create">Template erzeugen</button></div></div>';
    }
    var done = !!pair.uploaded_at;
    var badge = done
      ? '<span style="color:var(--ok);font-size:13px;font-weight:600">' + pair.glyph_count + " Buchstaben</span>"
      : '<span class="muted" style="font-size:13px">warte auf Upload</span>';
    var pdfUrl = "/api/handwriting/profile/" + state.profile.id + "/pair/" + idx + "/pdf";
    var prevUrl = state.pairPreviews[idx] ||
      (done ? "/files/templates/" + state.profile.id + "/pair-" + idx + "/glyph-preview.png?t=" + pair.uploaded_at : "");
    var prevHtml = prevUrl
      ? '<div style="margin-top:14px"><p class="muted" style="font-size:13px;margin-bottom:6px">Extrahierte Buchstaben:</p>' +
        '<img src="' + prevUrl + '" alt="Glyphen" style="max-width:100%;border:1px solid var(--border);border-radius:8px" /></div>'
      : "";
    return '<div class="pair-card card" data-pair="' + idx + '" style="padding:20px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center"><strong>Paar ' + num + "</strong>" + badge + "</div>" +
      '<div style="margin-top:12px"><a href="' + pdfUrl + '" class="btn btn-ghost" style="padding:8px 16px;font-size:13px" download>PDF herunterladen &amp; ausdrucken</a></div>' +
      '<div class="field-row" style="margin-top:14px">' +
      '<div style="flex:1"><label class="field">Seite 1 (Foto/Scan)</label><input type="file" class="pair-page1" accept="image/*" style="font-size:16px;padding:8px 0" /></div>' +
      '<div style="flex:1"><label class="field">Seite 2 (Foto/Scan)</label><input type="file" class="pair-page2" accept="image/*" style="font-size:16px;padding:8px 0" /></div></div>' +
      '<div style="margin-top:12px"><button class="btn btn-primary btn-pair-upload" disabled>Buchstaben extrahieren</button></div>' +
      prevHtml + "</div>";
  }

  function bindPairCards(root) {
    qa(".pair-card", root).forEach(function (card) {
      var idx = parseInt(card.getAttribute("data-pair"), 10);
      var btnC = card.querySelector(".btn-pair-create");
      if (btnC) btnC.addEventListener("click", function () { onCreatePair(idx, btnC); });
      var p1 = card.querySelector(".pair-page1");
      var p2 = card.querySelector(".pair-page2");
      if (p1) p1.addEventListener("change", function () { onPageSelected(idx, 1, p1.files[0], card); });
      if (p2) p2.addEventListener("change", function () { onPageSelected(idx, 2, p2.files[0], card); });
      var btnU = card.querySelector(".btn-pair-upload");
      if (btnU) btnU.addEventListener("click", function () { onUploadPair(idx, btnU); });
    });
  }

  function onCreatePair(idx, btn) {
    if (!state.activeId) return;
    var reset = showSpinner(btn, "Erzeuge…");
    msg(getEl("pair-status"), "Paar " + (idx + 1) + " wird erzeugt…");
    API.createPair(state.activeId, idx)
      .then(function () { return API.getProfile(state.activeId); })
      .then(function (p) { state.profile = p; renderPairs(); msg(getEl("pair-status"), "Paar " + (idx + 1) + " erzeugt. PDF herunterladen, ausdrucken, ausfüllen, Fotos hochladen.", "ok"); })
      .catch(function (e) { msg(getEl("pair-status"), "Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  function onPageSelected(idx, pageNum, file, card) {
    state.pairFiles[idx] = state.pairFiles[idx] || {};
    state.pairFiles[idx][pageNum] = file || null;
    var btn = card.querySelector(".btn-pair-upload");
    if (btn) btn.disabled = !(state.pairFiles[idx][1] && state.pairFiles[idx][2]);
  }

  function onUploadPair(idx, btn) {
    var files = state.pairFiles[idx] || {};
    if (!files[1] || !files[2]) return;
    var reset = showSpinner(btn, "Extrahiere…");
    msg(getEl("pair-status"), "Paar " + (idx + 1) + ": Buchstaben werden extrahiert…");
    API.uploadPair(state.activeId, idx, files[1], files[2])
      .then(function (res) {
        if (res.preview_url) state.pairPreviews[idx] = res.preview_url + "?t=" + Date.now();
        state.profile = res.profile;
        state.pairFiles[idx] = {};
        renderPairs();
        updateRenderButton();
        msg(getEl("pair-status"), "Paar " + (idx + 1) + ": " + res.glyph_count + " Buchstaben extrahiert!", "ok");
      })
      .catch(function (e) { msg(getEl("pair-status"), "Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  // ---- Auto-save ----
  var saveNameTimer, saveSettingsTimer;
  function autoSaveName() {
    clearTimeout(saveNameTimer);
    saveNameTimer = setTimeout(function () {
      var el = getEl("profile-name");
      var name = el ? el.value.trim() : "";
      if (!name || !state.activeId) return;
      API.renameProfile(state.activeId, name).then(function (p) { state.profile = p; }).catch(function () {});
    }, 600);
  }
  function autoSaveSettings() {
    clearTimeout(saveSettingsTimer);
    saveSettingsTimer = setTimeout(function () {
      if (!state.activeId) return;
      var sz = getEl("s-size"), th = getEl("s-thickness"), sh = getEl("s-sheet"), ink = getEl("s-ink");
      API.updateProfileSettings(state.activeId, {
        size_scale: sz ? parseFloat(sz.value) : 1.0,
        thickness: th ? parseFloat(th.value) : 1.0,
        sheet_type: sh ? sh.value : "liniert",
        ink_color: ink ? ink.value : "#16306b",
      }).then(function (p) { state.profile = p; }).catch(function () {});
    }, 400);
  }

  // ---- Inline new-profile form ----
  function showNewProfileForm() {
    var form = getEl("new-profile-form");
    var inp = getEl("new-profile-name");
    var btn = getEl("btn-new-profile");
    if (form) form.style.display = "";
    if (btn) btn.style.display = "none";
    if (inp) { inp.value = ""; inp.focus(); }
  }
  function hideNewProfileForm() {
    var form = getEl("new-profile-form");
    var btn = getEl("btn-new-profile");
    if (form) form.style.display = "none";
    if (btn) btn.style.display = "";
  }
  function submitNewProfile() {
    var inp = getEl("new-profile-name");
    var name = inp ? inp.value.trim() : "";
    if (!name) return;
    hideNewProfileForm();
    createProfile(name);
  }

  // ---- Bind UI ----
  function bindUI() {
    // New profile – inline form
    on(getEl("btn-new-profile"), "click", showNewProfileForm);
    on(getEl("btn-new-cancel"), "click", hideNewProfileForm);
    on(getEl("btn-new-confirm"), "click", submitNewProfile);
    on(getEl("new-profile-name"), "keydown", function (e) {
      if (e.key === "Enter" || e.keyCode === 13) { e.preventDefault(); submitNewProfile(); }
    });

    // Back
    on(getEl("btn-back"), "click", function () {
      loadProfiles().then(showList);
    });

    // Delete
    on(getEl("btn-delete"), "click", function () {
      if (!state.activeId) return;
      var pName = state.profile ? state.profile.name : state.activeId;
      if (!confirm(pName + " wirklich löschen?")) return;
      API.deleteProfile(state.activeId).catch(function () {}).then(function () {
        return loadProfiles();
      }).then(showList);
    });

    // Auto-save name
    on(getEl("profile-name"), "input", autoSaveName);

    // Settings auto-save
    on(getEl("s-size"), "input", function () {
      var v = getEl("s-size-val");
      if (v) v.textContent = fmtScale(getEl("s-size").value);
      autoSaveSettings();
    });
    on(getEl("s-thickness"), "input", function () {
      var v = getEl("s-thickness-val");
      if (v) v.textContent = fmtScale(getEl("s-thickness").value);
      autoSaveSettings();
    });
    on(getEl("s-sheet"), "change", autoSaveSettings);
    on(getEl("s-ink"), "change", autoSaveSettings);

    // Add pair
    on(getEl("btn-pair-add"), "click", function () {
      if (!state.activeId || !state.profile) return;
      var used = {};
      (state.profile.pairs || []).forEach(function (p) { used[p.index] = true; });
      var free = -1;
      for (var i = 0; i < MAX_PAIRS; i++) { if (!used[i]) { free = i; break; } }
      if (free < 0) return;
      onCreatePair(free, getEl("btn-pair-add"));
    });

    // Tabs
    qa(".tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { activateTab(btn.getAttribute("data-tab")); });
    });

    // Render
    on(getEl("btn-render"), "click", renderText);
    on(getEl("btn-pdf"), "click", function () { doExport("pdf"); });
    on(getEl("btn-png"), "click", function () { doExport("png"); });
    on(getEl("btn-jpg"), "click", function () { doExport("jpg"); });
  }

  function createProfile(name) {
    API.createProfile(name).then(function (p) {
      return loadProfiles().then(function () { return openProfile(p.id); });
    }).catch(function (e) { alert("Fehler: " + e.message); });
  }

  // ---- Render ----
  function renderText() {
    if (!state.activeId) return;
    var textEl = getEl("text");
    var text = textEl ? textEl.value : "";
    if (!text.trim()) { msg(getEl("status"), "Bitte Text eingeben.", "err"); return; }
    var btn = getEl("btn-render");
    var reset = showSpinner(btn, "Rendere…");
    msg(getEl("status"), "Handschrift wird erzeugt…");
    API.render({ text: text, profile_id: state.activeId })
      .then(function (res) {
        state.projectId = res.project_id;
        renderPreview(res.preview_urls);
        [getEl("btn-pdf"), getEl("btn-png"), getEl("btn-jpg")].forEach(function (b) { if (b) b.disabled = false; });
        msg(getEl("status"), "Fertig — " + res.pages + " Seite(n).", "ok");
      })
      .catch(function (e) { msg(getEl("status"), "Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  function renderPreview(urls) {
    var el = getEl("preview");
    if (!el) return;
    el.innerHTML = urls.length
      ? urls.map(function (u) { return '<div class="page-shadow"><img src="' + u + '" alt="Vorschau" /></div>'; }).join("")
      : '<div class="empty-state">Keine Seiten.</div>';
  }

  function doExport(fmt) {
    if (!state.projectId) return;
    var btnMap = { pdf: "btn-pdf", png: "btn-png", jpg: "btn-jpg" };
    var btn = getEl(btnMap[fmt]);
    var reset = showSpinner(btn, fmt.toUpperCase());
    API.exportHandwriting(state.projectId, fmt)
      .then(function (res) {
        var a = document.createElement("a");
        a.href = res.url;
        a.download = "";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        msg(getEl("status"), "Export fertig.", "ok");
      })
      .catch(function (e) { msg(getEl("status"), "Export: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  // ---- Utils ----
  function msg(el, text, kind) {
    setStatus(el, text, kind);
    if (el) el.style.display = text ? "" : "none";
  }
  function fmtScale(v) { return Number(v).toFixed(2).replace(/0$/, "") + "×"; }
})();
