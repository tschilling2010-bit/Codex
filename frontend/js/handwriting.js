(function () {
  "use strict";
  var MAX_VARIANTS = 4;
  var state = { profiles: [], activeId: null, profile: null, projectId: null, variantFiles: {} };

  function getEl(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function on(el, evt, fn) { if (el) el.addEventListener(evt, fn); }

  document.addEventListener("DOMContentLoaded", function () {
    try { bindUI(); } catch (e) { console.error("bindUI error:", e); }
    loadProfiles().then(function () {
      if (state.profiles.length === 0) {
        ProfileCache.restoreAll(function (count) {
          if (count > 0) {
            loadProfiles();
          }
        });
      }
    }).catch(function (e) { console.error("loadProfiles error:", e); });
  });

  // ---- Views ----
  function showList() {
    state.activeId = null;
    state.profile = null;
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "";
    if (vd) vd.style.display = "none";
    hideNewProfileForm();
    closeSettingsPanel();
  }
  function showDetail() {
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "none";
    if (vd) vd.style.display = "";
  }

  // ---- Settings panel (slide-in) ----
  function openSettingsPanel() {
    var panel = getEl("settings-panel");
    var overlay = getEl("settings-overlay");
    if (panel) panel.classList.add("open");
    if (overlay) overlay.classList.add("visible");
  }
  function closeSettingsPanel() {
    var panel = getEl("settings-panel");
    var overlay = getEl("settings-overlay");
    if (panel) panel.classList.remove("open");
    if (overlay) overlay.classList.remove("visible");
  }

  // ---- Collapsible settings ----
  function toggleCollapsible() {
    var el = getEl("settings-collapsible");
    if (el) el.classList.toggle("open");
  }

  // ---- Profiles ----
  function loadProfiles() {
    var grid = getEl("profile-grid");
    return API.listProfiles().then(function (list) {
      state.profiles = list;
      renderProfileGrid();
    }).catch(function (e) {
      if (grid) grid.innerHTML = '<p class="muted">Fehler: ' + escapeHtml(e.message) + "</p>";
    });
  }

  function renderProfileGrid() {
    var grid = getEl("profile-grid");
    if (!grid) return;
    if (state.profiles.length === 0) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Noch keine Schriften erstellt.</div>';
      return;
    }
    grid.innerHTML = state.profiles.map(function (p) {
      var badge = p.glyph_count > 0
        ? '<span style="color:var(--ok);font-size:13px">' + p.glyph_count + " Glyphen</span>"
        : '<span class="muted" style="font-size:13px">Keine Vorlagen</span>';
      return '<a class="card interactive" data-id="' + p.id + '" href="#">' +
        "<h3>" + escapeHtml(p.name) + "</h3>" +
        "<p>" + badge + "</p></a>";
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
    state.variantFiles = {};
    return API.getProfile(id).then(function (p) {
      state.profile = p;
      showDetail();
      var nameEl = getEl("profile-name");
      if (nameEl) nameEl.value = p.name;
      applySettingsToUI(p.settings);
      ensureFirstVariant().then(function () {
        renderVariants();
        updateTemplateLink();
        updateRenderButton();
      });
    }).catch(function (e) {
      alert("Fehler: " + e.message);
    });
  }

  function ensureFirstVariant() {
    var pairs = (state.profile && state.profile.pairs) || [];
    if (pairs.length > 0) return Promise.resolve();
    return API.createPair(state.activeId, 0)
      .then(function () { return API.getProfile(state.activeId); })
      .then(function (p) { state.profile = p; });
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
    msg(st, ok ? "Bereit." : "Lade zuerst Vorlagen hoch.");
  }

  function updateTemplateLink() {
    var link = getEl("template-download");
    if (!link || !state.activeId) return;
    link.href = "/api/handwriting/profile/" + state.activeId + "/pair/0/pdf";
  }

  // ---- Variants ----
  function renderVariants() {
    var list = getEl("variants-list");
    var addBtn = getEl("btn-variant-add");
    if (!list || !state.profile) return;
    var pairs = state.profile.pairs || [];
    var html = [];
    for (var i = 0; i < pairs.length; i++) {
      html.push(variantCardHTML(pairs[i]));
    }
    if (html.length === 0) {
      html.push('<div class="empty-state">Keine Varianten vorhanden.</div>');
    }
    list.innerHTML = html.join("");
    bindVariantCards(list);
    if (addBtn) {
      addBtn.disabled = pairs.length >= MAX_VARIANTS;
    }
  }

  function variantCardHTML(pair) {
    var idx = pair.index;
    var num = idx + 1;
    var done = !!pair.uploaded_at;
    var statusHtml = done
      ? '<span style="color:var(--ok);font-size:13px;font-weight:600">' + pair.glyph_count + " Glyphen</span>"
      : '<span class="muted" style="font-size:13px">Noch nicht hochgeladen</span>';

    return '<div class="variant-card card" data-variant="' + idx + '" style="padding:18px 22px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">' +
      "<strong>Variante " + num + "</strong>" + statusHtml + "</div>" +
      '<div class="field-row">' +
      '<div style="flex:1"><label class="field">Seite 1 (Buchstaben)</label>' +
      '<input type="file" class="var-page1" accept="image/*" style="font-size:16px;padding:4px 0;width:100%" /></div>' +
      '<div style="flex:1"><label class="field">Seite 2 (Sonderzeichen)</label>' +
      '<input type="file" class="var-page2" accept="image/*" style="font-size:16px;padding:4px 0;width:100%" /></div></div>' +
      '<div style="margin-top:12px"><button class="btn btn-primary btn-var-upload" disabled>Hochladen</button></div>' +
      "</div>";
  }

  function bindVariantCards(root) {
    qa(".variant-card", root).forEach(function (card) {
      var idx = parseInt(card.getAttribute("data-variant"), 10);
      var p1 = card.querySelector(".var-page1");
      var p2 = card.querySelector(".var-page2");
      if (p1) p1.addEventListener("change", function () { onFileSelected(idx, 1, p1.files[0], card); });
      if (p2) p2.addEventListener("change", function () { onFileSelected(idx, 2, p2.files[0], card); });
      var btnU = card.querySelector(".btn-var-upload");
      if (btnU) btnU.addEventListener("click", function () { onUploadVariant(idx, btnU); });
    });
  }

  function onFileSelected(idx, pageNum, file, card) {
    state.variantFiles[idx] = state.variantFiles[idx] || {};
    state.variantFiles[idx][pageNum] = file || null;
    var btn = card.querySelector(".btn-var-upload");
    if (btn) btn.disabled = !(state.variantFiles[idx][1] && state.variantFiles[idx][2]);
  }

  function onUploadVariant(idx, btn) {
    var files = state.variantFiles[idx] || {};
    if (!files[1] || !files[2]) return;
    var reset = showSpinner(btn, "Extrahiere…");
    msg(getEl("pair-status"), "Variante " + (idx + 1) + ": Buchstaben werden extrahiert…");
    if (getEl("pair-status")) getEl("pair-status").style.display = "";
    API.uploadPair(state.activeId, idx, files[1], files[2])
      .then(function (res) {
        state.profile = res.profile;
        state.variantFiles[idx] = {};
        renderVariants();
        updateRenderButton();
        msg(getEl("pair-status"), "Variante " + (idx + 1) + ": " + res.glyph_count + " Glyphen extrahiert!", "ok");
        ProfileCache.save(state.activeId, function () {});
      })
      .catch(function (e) { msg(getEl("pair-status"), "Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  function onAddVariant() {
    if (!state.activeId || !state.profile) return;
    var pairs = state.profile.pairs || [];
    if (pairs.length >= MAX_VARIANTS) return;
    var used = {};
    pairs.forEach(function (p) { used[p.index] = true; });
    var free = -1;
    for (var i = 0; i < MAX_VARIANTS; i++) { if (!used[i]) { free = i; break; } }
    if (free < 0) return;
    var btn = getEl("btn-variant-add");
    var reset = showSpinner(btn, "Erstelle…");
    API.createPair(state.activeId, free)
      .then(function () { return API.getProfile(state.activeId); })
      .then(function (p) { state.profile = p; renderVariants(); msg(getEl("pair-status"), "Variante " + (free + 1) + " erstellt.", "ok"); })
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
      API.renameProfile(state.activeId, name).then(function (p) {
        state.profile = p;
        ProfileCache.save(state.activeId, function () {});
      }).catch(function () {});
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
        ink_color: ink ? ink.value : "#000000",
      }).then(function (p) {
        state.profile = p;
        ProfileCache.save(state.activeId, function () {});
      }).catch(function () {});
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
    on(getEl("btn-new-profile"), "click", showNewProfileForm);
    on(getEl("btn-new-cancel"), "click", hideNewProfileForm);
    on(getEl("btn-new-confirm"), "click", submitNewProfile);
    on(getEl("new-profile-name"), "keydown", function (e) {
      if (e.key === "Enter" || e.keyCode === 13) { e.preventDefault(); submitNewProfile(); }
    });

    on(getEl("btn-back"), "click", function () {
      loadProfiles().then(showList);
    });

    on(getEl("btn-delete"), "click", function () {
      if (!state.activeId) return;
      var pName = state.profile ? state.profile.name : state.activeId;
      if (!confirm(pName + " wirklich löschen?")) return;
      ProfileCache.remove(state.activeId, function () {});
      API.deleteProfile(state.activeId).catch(function () {}).then(function () {
        return loadProfiles();
      }).then(showList);
    });

    on(getEl("profile-name"), "input", autoSaveName);

    // Gear button opens slide-in template panel
    on(getEl("btn-gear"), "click", openSettingsPanel);
    on(getEl("btn-panel-close"), "click", closeSettingsPanel);
    on(getEl("settings-overlay"), "click", closeSettingsPanel);

    // Collapsible settings toggle
    on(getEl("settings-toggle"), "click", toggleCollapsible);

    // Settings sliders and inputs
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

    on(getEl("btn-variant-add"), "click", onAddVariant);

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
