(function () {
  "use strict";
  var MAX_VARIANTS = 4;
  var MAX_COLORS = 8;
  var HL_FAV_KEY = "hefterpro_hl_favs";
  var state = {
    profiles: [], activeId: null, profile: null,
    projectId: null, variantFiles: {},
    wordMap: [], pageWidth: 0, pageHeight: 0,
    highlights: {}, activeHlColor: null, hlMode: "marker",
    hlFavorites: [], rangeStart: null, rangeMode: false
  };

  var serverHlTimer;
  var textHlRendered = false;
  var longPressFired = false;

  function getEl(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function on(el, evt, fn) { if (el) el.addEventListener(evt, fn); }

  // ---- Init ----
  document.addEventListener("DOMContentLoaded", function () {
    loadHlFavorites();
    renderHlFavorites();
    try { bindUI(); } catch (e) { console.error("bindUI error:", e); }
    loadProfiles().then(function () {
      if (state.profiles.length === 0) {
        ProfileCache.restoreAll(function (count) {
          if (count > 0) { loadProfiles(); }
        });
      }
    }).catch(function (e) { console.error("loadProfiles error:", e); });
  });

  // ---- Profile dropdown ----
  var dropdownOpen = false;
  function toggleDropdown() {
    dropdownOpen = !dropdownOpen;
    var dd = getEl("profile-dropdown");
    if (dd) dd.style.display = dropdownOpen ? "" : "none";
    if (dropdownOpen) renderDropdownList();
  }
  function closeDropdown() {
    dropdownOpen = false;
    var dd = getEl("profile-dropdown");
    if (dd) dd.style.display = "none";
    var inl = getEl("new-profile-inline");
    if (inl) inl.style.display = "none";
  }

  function renderDropdownList() {
    var list = getEl("profile-dropdown-list");
    if (!list) return;
    if (state.profiles.length === 0) {
      list.innerHTML = '<div style="padding:8px 14px;color:var(--text-muted);font-size:13px">Keine Schriften</div>';
      return;
    }
    list.innerHTML = state.profiles.map(function (p) {
      var cls = "dropdown-item" + (p.id === state.activeId ? " active" : "");
      var badge = p.glyph_count > 0 ? " (" + p.glyph_count + ")" : "";
      return '<button class="' + cls + '" data-id="' + p.id + '" type="button">' +
        escapeHtml(p.name) + '<span class="muted" style="font-size:12px">' + badge + '</span></button>';
    }).join("");
    qa(".dropdown-item[data-id]", list).forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeDropdown();
        selectProfile(btn.getAttribute("data-id"));
      });
    });
  }

  function showInlineNew() {
    var inl = getEl("new-profile-inline");
    var inp = getEl("new-profile-name");
    if (inl) inl.style.display = "";
    if (inp) { inp.value = ""; inp.focus(); }
  }
  function submitNewProfile() {
    var inp = getEl("new-profile-name");
    var name = inp ? inp.value.trim() : "";
    if (!name) return;
    closeDropdown();
    API.createProfile(name).then(function (p) {
      return loadProfiles().then(function () { selectProfile(p.id); });
    }).catch(function (e) { alert("Fehler: " + e.message); });
  }

  // ---- Profiles ----
  function loadProfiles() {
    return API.listProfiles().then(function (list) {
      state.profiles = list;
      if (list.length > 0 && !state.activeId) {
        selectProfile(list[0].id);
      } else if (state.activeId) {
        updateProfileBtnName();
      }
      if (list.length === 0) {
        updateProfileBtnName();
        updateRenderButton();
      }
    }).catch(function (err) {
      console.error("loadProfiles:", err);
    });
  }

  function selectProfile(id) {
    state.activeId = id;
    state.variantFiles = {};
    state.highlights = {};
    state.activeHlColor = null;
    state.projectId = null;
    clearHlSelection();
    hideHighlightBar();
    clearPreview();
    return API.getProfile(id).then(function (p) {
      state.profile = p;
      updateProfileBtnName();
      applySettingsToUI(p.settings);
      return ensureFirstVariant().then(function () {
        renderVariants();
        updateTemplateLink();
        updateRenderButton();
      });
    }).catch(function (e) {
      console.error("selectProfile:", e);
      statusMsg("Fehler: " + e.message, "err");
    });
  }

  function updateProfileBtnName() {
    var el = getEl("profile-btn-name");
    if (!el) return;
    if (state.profile) {
      el.textContent = state.profile.name;
    } else if (state.profiles.length === 0) {
      el.textContent = "Schrift erstellen…";
    } else {
      el.textContent = "Schrift wählen…";
    }
  }

  function clearPreview() {
    var el = getEl("preview");
    if (el) el.innerHTML = '<div class="empty-state-nice"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="opacity:.4"><path d="M12 2l2 6.5L21 11l-7 2.5L12 20l-2-6.5L3 11l7-2.5L12 2z"/></svg><p>Text eingeben und „Rendern“ klicken.</p></div>';
    var expBtn = getEl("btn-export");
    if (expBtn) expBtn.disabled = true;
  }

  function ensureFirstVariant() {
    var pairs = (state.profile && state.profile.pairs) || [];
    if (pairs.length > 0) return Promise.resolve();
    return API.createPair(state.activeId, 0)
      .then(function () { return API.getProfile(state.activeId); })
      .then(function (p) { state.profile = p; });
  }

  // ---- Settings panel ----
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

  // ---- Settings ----
  function applySettingsToUI(s) {
    if (!s) return;
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
    if (btn) btn.disabled = !ok;
    statusMsg(ok ? "" : "Lade zuerst Vorlagen hoch.");
  }

  function updateTemplateLink() {
    var link = getEl("template-download");
    if (!link || !state.activeId) return;
    link.href = "/api/handwriting/profile/" + state.activeId + "/pair/0/pdf";
  }

  // ---- Status helper ----
  function statusMsg(text, kind) {
    var el = getEl("status");
    if (!el) return;
    el.className = "status-inline" + (kind ? " " + kind : "");
    el.textContent = text || "";
  }

  function pairMsg(text, kind) {
    var el = getEl("pair-status");
    if (!el) return;
    el.className = "status" + (kind ? " " + kind : "");
    el.textContent = text || "";
    el.style.display = text ? "" : "none";
  }

  // ---- Variants ----
  function renderVariants() {
    var list = getEl("variants-list");
    var addBtn = getEl("btn-variant-add");
    if (!list || !state.profile) return;
    var pairs = state.profile.pairs || [];
    var html = [];
    for (var i = 0; i < pairs.length; i++) { html.push(variantCardHTML(pairs[i])); }
    if (html.length === 0) html.push('<div class="empty-state">Keine Varianten vorhanden.</div>');
    list.innerHTML = html.join("");
    bindVariantCards(list);
    if (addBtn) addBtn.disabled = pairs.length >= MAX_VARIANTS;
  }

  function variantCardHTML(pair) {
    var idx = pair.index, num = idx + 1;
    var done = !!pair.uploaded_at;
    var statusHtml = done
      ? '<span style="color:var(--ok);font-size:13px;font-weight:600">' + pair.glyph_count + " Glyphen</span>"
      : '<span class="muted" style="font-size:13px">Noch nicht hochgeladen</span>';
    return '<div class="variant-card card" data-variant="' + idx + '" style="padding:16px 20px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">' +
      "<strong>Variante " + num + "</strong>" + statusHtml + "</div>" +
      '<div class="field-row">' +
      '<div style="flex:1"><label class="field">Seite 1</label>' +
      '<input type="file" class="var-page1" accept="image/*" style="font-size:15px;width:100%" /></div>' +
      '<div style="flex:1"><label class="field">Seite 2</label>' +
      '<input type="file" class="var-page2" accept="image/*" style="font-size:15px;width:100%" /></div></div>' +
      '<div style="margin-top:10px"><button class="btn btn-primary btn-sm btn-var-upload" disabled>Hochladen</button></div></div>';
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
    pairMsg("Variante " + (idx + 1) + ": wird extrahiert…");
    API.uploadPair(state.activeId, idx, files[1], files[2])
      .then(function (res) {
        state.profile = res.profile;
        state.variantFiles[idx] = {};
        renderVariants();
        updateRenderButton();
        pairMsg("Variante " + (idx + 1) + ": " + res.glyph_count + " Glyphen!", "ok");
        ProfileCache.save(state.activeId, function () {});
      })
      .catch(function (e) { pairMsg("Fehler: " + e.message, "err"); })
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
      .then(function (p) { state.profile = p; renderVariants(); })
      .catch(function (e) { pairMsg("Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  // ---- Auto-save ----
  var saveSettingsTimer;
  function autoSaveSettings() {
    clearTimeout(saveSettingsTimer);
    saveSettingsTimer = setTimeout(function () {
      if (!state.activeId) return;
      var sz = getEl("s-size"), th = getEl("s-thickness"), sh = getEl("s-sheet"), ink = getEl("s-ink");
      API.updateProfileSettings(state.activeId, {
        size_scale: sz ? parseFloat(sz.value) : 1.0,
        thickness: th ? parseFloat(th.value) : 1.0,
        sheet_type: sh ? sh.value : "liniert",
        ink_color: ink ? ink.value : "#000000"
      }).then(function (p) {
        state.profile = p;
        ProfileCache.save(state.activeId, function () {});
      }).catch(function () {});
    }, 400);
  }

  // ---- Highlight system ----

  function selectHlColor(color) {
    qa(".hl-color.active").forEach(function (b) { b.classList.remove("active"); });
    state.activeHlColor = color;
    qa(".hl-color[data-color]").forEach(function (b) {
      if (b.getAttribute("data-color") === color) b.classList.add("active");
    });
  }

  function clearHlSelection() {
    qa(".hl-color.active").forEach(function (b) { b.classList.remove("active"); });
    state.activeHlColor = null;
  }

  function hideHighlightBar() {
    var bar = getEl("highlight-bar");
    if (bar) bar.style.display = "none";
  }

  function showHighlightBar() {
    var bar = getEl("highlight-bar");
    if (bar) bar.style.display = "";
    if (!state.activeHlColor && state.hlFavorites.length > 0) {
      selectHlColor(state.hlFavorites[0]);
    }
  }

  function onHlColorClick(e) {
    if (longPressFired) { longPressFired = false; return; }
    var btn = e.currentTarget;
    var color = btn.getAttribute("data-color");
    if (state.activeHlColor === color) return;
    selectHlColor(color);
  }

  function onHlModeClick(e) {
    var btn = e.currentTarget;
    var mode = btn.getAttribute("data-mode");
    state.hlMode = mode;
    state.rangeStart = null;
    qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
    qa(".hl-mode-btn").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    if (mode === "eraser") {
      clearHlSelection();
    } else if (!state.activeHlColor && state.hlFavorites.length > 0) {
      selectHlColor(state.hlFavorites[0]);
    }
  }

  function onAddColorClick() {
    var panel = getEl("hl-add-panel");
    if (panel) panel.style.display = panel.style.display === "none" ? "flex" : "none";
  }

  function onConfirmColor() {
    var picker = getEl("hl-color-picker");
    if (!picker || state.hlFavorites.length >= MAX_COLORS) return;
    var color = picker.value;
    var panel = getEl("hl-add-panel");
    if (state.hlFavorites.indexOf(color) >= 0) {
      selectHlColor(color);
    } else {
      state.hlFavorites.push(color);
      saveHlFavorites();
      renderHlFavorites();
      selectHlColor(color);
    }
    if (panel) panel.style.display = "none";
    if (state.hlMode === "eraser") {
      state.hlMode = "marker";
      qa(".hl-mode-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-mode") === "marker");
      });
    }
  }

  function loadHlFavorites() {
    try {
      var raw = localStorage.getItem(HL_FAV_KEY);
      state.hlFavorites = raw ? JSON.parse(raw) : [];
    } catch (e) { state.hlFavorites = []; }
  }
  function saveHlFavorites() {
    try { localStorage.setItem(HL_FAV_KEY, JSON.stringify(state.hlFavorites)); } catch (e) {}
  }

  function renderHlFavorites() {
    var container = getEl("hl-favorites");
    if (!container) return;
    container.innerHTML = state.hlFavorites.map(function (c) {
      return '<button class="hl-color hl-fav" data-color="' + c + '" style="background:' + c + '" type="button"></button>';
    }).join("");
    qa(".hl-fav", container).forEach(function (btn) {
      btn.addEventListener("click", onHlColorClick);
      bindLongPress(btn, function () { showColorContextMenu(btn); });
    });
    var addBtn = getEl("btn-hl-add");
    if (addBtn) addBtn.style.display = state.hlFavorites.length >= MAX_COLORS ? "none" : "";
  }

  function bindLongPress(el, callback) {
    var timer = null;
    function start() {
      timer = setTimeout(function () {
        longPressFired = true;
        callback();
      }, 500);
    }
    function cancel() { clearTimeout(timer); }
    el.addEventListener("mousedown", start);
    el.addEventListener("mouseup", cancel);
    el.addEventListener("mouseleave", cancel);
    el.addEventListener("touchstart", start, { passive: true });
    el.addEventListener("touchend", cancel);
    el.addEventListener("touchmove", cancel);
    el.addEventListener("touchcancel", cancel);
    el.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  }

  function showColorContextMenu(btn) {
    closeContextMenu();
    var color = btn.getAttribute("data-color");
    var rect = btn.getBoundingClientRect();
    var menu = document.createElement("div");
    menu.className = "hl-context-menu";
    menu.innerHTML =
      '<label class="ctx-item ctx-edit-label">Bearbeiten' +
      '<input type="color" class="ctx-edit-picker" value="' + color + '" /></label>' +
      '<button class="ctx-item ctx-delete" data-action="delete" type="button">Löschen</button>';
    menu.style.position = "fixed";
    menu.style.left = Math.max(8, rect.left) + "px";
    menu.style.top = (rect.bottom + 8) + "px";
    document.body.appendChild(menu);
    var editPicker = menu.querySelector(".ctx-edit-picker");
    editPicker.addEventListener("change", function () {
      var newColor = editPicker.value;
      var idx = state.hlFavorites.indexOf(color);
      if (idx >= 0) state.hlFavorites[idx] = newColor;
      var keys = Object.keys(state.highlights);
      for (var i = 0; i < keys.length; i++) {
        if (state.highlights[keys[i]].color === color) state.highlights[keys[i]].color = newColor;
      }
      if (state.activeHlColor === color) state.activeHlColor = newColor;
      saveHlFavorites();
      renderHlFavorites();
      selectHlColor(newColor);
      refreshHlRegions();
      scheduleServerHighlight();
      closeContextMenu();
    });
    menu.querySelector('[data-action="delete"]').addEventListener("click", function () {
      state.hlFavorites = state.hlFavorites.filter(function (c) { return c !== color; });
      if (state.activeHlColor === color) {
        state.activeHlColor = state.hlFavorites.length > 0 ? state.hlFavorites[0] : null;
        if (state.activeHlColor) selectHlColor(state.activeHlColor);
      }
      saveHlFavorites();
      renderHlFavorites();
      closeContextMenu();
    });
    setTimeout(function () {
      document.addEventListener("click", closeContextMenu);
      document.addEventListener("touchstart", closeContextMenu);
    }, 50);
  }

  function closeContextMenu() {
    var m = document.querySelector(".hl-context-menu");
    if (m && m.parentNode) m.parentNode.removeChild(m);
    document.removeEventListener("click", closeContextMenu);
    document.removeEventListener("touchstart", closeContextMenu);
  }

  function hexToRgba(hex, alpha) {
    hex = hex.replace("#", "");
    var r = parseInt(hex.substring(0, 2), 16);
    var g = parseInt(hex.substring(2, 4), 16);
    var b = parseInt(hex.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }

  function hexToPastel(hex, strength) {
    hex = hex.replace("#", "");
    var r = parseInt(hex.substring(0, 2), 16);
    var g = parseInt(hex.substring(2, 4), 16);
    var b = parseInt(hex.substring(4, 6), 16);
    r = Math.round(255 - (255 - r) * strength);
    g = Math.round(255 - (255 - g) * strength);
    b = Math.round(255 - (255 - b) * strength);
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  function onWordClick(e) {
    var el = e.currentTarget;
    var idx = parseInt(el.getAttribute("data-word-idx"), 10);
    if (isNaN(idx)) return;

    if (state.hlMode === "eraser") {
      if (!state.rangeMode) {
        delete state.highlights[idx];
      } else {
        if (state.rangeStart === null) {
          state.rangeStart = idx;
          el.classList.add("hl-range-start");
          return;
        }
        var from = Math.min(state.rangeStart, idx);
        var to = Math.max(state.rangeStart, idx);
        qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
        for (var i = from; i <= to; i++) { delete state.highlights[i]; }
        state.rangeStart = null;
      }
      refreshHlRegions();
      scheduleServerHighlight();
      return;
    }

    if (!state.activeHlColor) {
      if (state.hlFavorites.length > 0) { selectHlColor(state.hlFavorites[0]); }
      else return;
    }

    if (!state.rangeMode) {
      var cur = state.highlights[idx];
      if (cur && cur.color === state.activeHlColor && cur.mode === state.hlMode) {
        delete state.highlights[idx];
      } else {
        state.highlights[idx] = { color: state.activeHlColor, mode: state.hlMode };
      }
    } else {
      if (state.rangeStart === null) {
        state.rangeStart = idx;
        el.classList.add("hl-range-start");
        return;
      }
      var from2 = Math.min(state.rangeStart, idx);
      var to2 = Math.max(state.rangeStart, idx);
      qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
      if (from2 === to2) {
        var cur2 = state.highlights[idx];
        if (cur2 && cur2.color === state.activeHlColor && cur2.mode === state.hlMode) {
          delete state.highlights[idx];
        } else {
          state.highlights[idx] = { color: state.activeHlColor, mode: state.hlMode };
        }
      } else {
        for (var j = from2; j <= to2; j++) {
          if (state.wordMap[j]) {
            state.highlights[j] = { color: state.activeHlColor, mode: state.hlMode };
          }
        }
      }
      state.rangeStart = null;
    }

    refreshHlRegions();
    scheduleServerHighlight();
  }

  function onRangeModeToggle() {
    state.rangeMode = !state.rangeMode;
    state.rangeStart = null;
    qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
    var btn = getEl("btn-hl-range");
    if (btn) btn.classList.toggle("active", state.rangeMode);
  }

  function clearAllHighlights() {
    state.highlights = {};
    state.rangeStart = null;
    qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
    refreshHlRegions();
    if (textHlRendered && state.projectId) {
      API.highlight(state.projectId, []).then(function (res) {
        if (res && res.preview_urls) refreshPreviewImages(res.preview_urls);
        textHlRendered = false;
      }).catch(function () {});
    }
  }

  function refreshHlRegions() {
    qa(".hl-region").forEach(function (el) { el.parentNode.removeChild(el); });
    qa(".word-overlay").forEach(function (el) { el.style.background = ""; });
    if (!state.wordMap.length || !state.pageWidth) return;

    var regions = computeMergedRegions();
    var containers = qa(".page-container");
    var PAD = 3;

    for (var r = 0; r < regions.length; r++) {
      var reg = regions[r];
      var container = containers[reg.page];
      if (!container) continue;
      var div = document.createElement("div");
      div.style.left = ((reg.x - PAD) / state.pageWidth * 100).toFixed(3) + "%";
      div.style.top = ((reg.y - PAD) / state.pageHeight * 100).toFixed(3) + "%";
      div.style.width = ((reg.w + PAD * 2) / state.pageWidth * 100).toFixed(3) + "%";
      div.style.height = ((reg.h + PAD * 2) / state.pageHeight * 100).toFixed(3) + "%";
      if (reg.mode === "marker") {
        div.className = "hl-region hl-marker";
        div.style.background = hexToPastel(reg.color, 0.35);
      } else {
        div.className = "hl-region hl-text";
        div.style.boxShadow = "inset 0 0 0 2px " + hexToRgba(reg.color, 0.35);
      }
      container.appendChild(div);
    }
  }

  function computeMergedRegions() {
    var keys = Object.keys(state.highlights);
    if (keys.length === 0) return [];

    var entries = [];
    for (var i = 0; i < keys.length; i++) {
      var idx = parseInt(keys[i], 10);
      var hl = state.highlights[idx];
      var wb = state.wordMap[idx];
      if (!wb) continue;
      entries.push({ idx: idx, wb: wb, color: hl.color, mode: hl.mode });
    }
    entries.sort(function (a, b) { return a.idx - b.idx; });

    var regions = [];
    var cur = null;
    for (var j = 0; j < entries.length; j++) {
      var e = entries[j];
      if (cur && cur.color === e.color && cur.mode === e.mode &&
          cur.y === e.wb.y && e.idx === cur.lastIdx + 1 && cur.mode === "marker") {
        cur.w = e.wb.x + e.wb.w - cur.x;
        cur.lastIdx = e.idx;
      } else {
        if (cur) regions.push(cur);
        cur = {
          page: e.wb.page, x: e.wb.x, y: e.wb.y, w: e.wb.w, h: e.wb.h,
          color: e.color, mode: e.mode, lastIdx: e.idx
        };
      }
    }
    if (cur) regions.push(cur);
    return regions;
  }

  function getHighlightList() {
    var list = [];
    var keys = Object.keys(state.highlights);
    for (var i = 0; i < keys.length; i++) {
      var idx = parseInt(keys[i], 10);
      var hl = state.highlights[idx];
      list.push({ word_index: idx, color: hl.color, mode: hl.mode });
    }
    return list;
  }

  function applyHighlightsToServer() {
    var hl = getHighlightList();
    if (hl.length === 0 || !state.projectId) return Promise.resolve();
    return API.highlight(state.projectId, hl);
  }

  function scheduleServerHighlight() {
    var hasText = false;
    var keys = Object.keys(state.highlights);
    for (var i = 0; i < keys.length; i++) {
      if (state.highlights[keys[i]].mode === "text") { hasText = true; break; }
    }
    if (!hasText && !textHlRendered) return;
    clearTimeout(serverHlTimer);
    serverHlTimer = setTimeout(function () {
      if (!state.projectId) return;
      var textHl = [];
      var allKeys = Object.keys(state.highlights);
      for (var j = 0; j < allKeys.length; j++) {
        var idx = parseInt(allKeys[j], 10);
        var hl = state.highlights[allKeys[j]];
        if (hl.mode === "text") {
          textHl.push({ word_index: idx, color: hl.color, mode: hl.mode });
        }
      }
      var toSend = textHl.length > 0 ? textHl : [];
      API.highlight(state.projectId, toSend).then(function (res) {
        if (res && res.preview_urls) refreshPreviewImages(res.preview_urls);
        textHlRendered = textHl.length > 0;
      }).catch(function () {});
    }, 400);
  }

  function refreshPreviewImages(urls) {
    var containers = qa(".page-container");
    for (var i = 0; i < containers.length && i < urls.length; i++) {
      var img = containers[i].querySelector("img");
      if (img) img.src = urls[i] + "?t=" + Date.now();
    }
  }

  // ---- Bind UI ----
  function bindUI() {
    // Profile dropdown
    on(getEl("profile-btn"), "click", toggleDropdown);
    on(getEl("btn-add-profile"), "click", showInlineNew);
    on(getEl("btn-new-confirm"), "click", submitNewProfile);
    on(getEl("btn-new-cancel"), "click", function () {
      var inl = getEl("new-profile-inline");
      if (inl) inl.style.display = "none";
    });
    on(getEl("new-profile-name"), "keydown", function (e) {
      if (e.key === "Enter" || e.keyCode === 13) { e.preventDefault(); submitNewProfile(); }
    });
    document.addEventListener("click", function (e) {
      var sel = getEl("profile-selector");
      if (sel && !sel.contains(e.target) && dropdownOpen) closeDropdown();
    });

    // Delete profile
    on(getEl("btn-delete"), "click", function () {
      if (!state.activeId) return;
      var pName = state.profile ? state.profile.name : state.activeId;
      if (!confirm(pName + " wirklich löschen?")) return;
      ProfileCache.remove(state.activeId, function () {});
      API.deleteProfile(state.activeId).catch(function () {}).then(function () {
        state.activeId = null;
        state.profile = null;
        closeSettingsPanel();
        return loadProfiles();
      });
    });

    // Gear / settings panel
    on(getEl("btn-gear"), "click", openSettingsPanel);
    on(getEl("btn-panel-close"), "click", closeSettingsPanel);
    on(getEl("settings-overlay"), "click", closeSettingsPanel);

    // Settings sliders
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

    // Variants
    on(getEl("btn-variant-add"), "click", onAddVariant);

    // Render
    on(getEl("btn-render"), "click", renderText);

    // Export dropdown
    on(getEl("btn-export"), "click", function (e) {
      e.stopPropagation();
      var menu = getEl("export-menu");
      if (!menu) return;
      menu.style.display = menu.style.display === "none" ? "" : "none";
    });
    qa(".export-opt").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var fmt = btn.getAttribute("data-fmt");
        var menu = getEl("export-menu");
        if (menu) menu.style.display = "none";
        doExport(fmt);
      });
    });
    document.addEventListener("click", function (e) {
      var wrap = getEl("export-wrap");
      var menu = getEl("export-menu");
      if (wrap && menu && !wrap.contains(e.target)) menu.style.display = "none";
    });

    // Highlight
    qa(".hl-mode-btn").forEach(function (btn) { btn.addEventListener("click", onHlModeClick); });
    on(getEl("btn-hl-add"), "click", onAddColorClick);
    on(getEl("btn-hl-confirm"), "click", onConfirmColor);
    on(getEl("btn-hl-clear"), "click", clearAllHighlights);
    on(getEl("btn-hl-range"), "click", onRangeModeToggle);
  }

  // ---- Render ----
  function renderText() {
    if (!state.activeId) return;
    var textEl = getEl("text");
    var text = textEl ? textEl.value : "";
    if (!text.trim()) { statusMsg("Bitte Text eingeben.", "err"); return; }
    var btn = getEl("btn-render");
    var reset = showSpinner(btn, "Rendere…");
    statusMsg("Handschrift wird erzeugt…");
    state.highlights = {};
    state.activeHlColor = null;
    state.rangeStart = null;
    state.hlMode = "marker";
    textHlRendered = false;
    qa(".hl-range-start").forEach(function (r) { r.classList.remove("hl-range-start"); });
    qa(".hl-mode-btn").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === "marker");
    });
    clearHlSelection();
    API.render({ text: text, profile_id: state.activeId })
      .then(function (res) {
        state.projectId = res.project_id;
        state.wordMap = res.word_map || [];
        state.pageWidth = res.page_width || 1;
        state.pageHeight = res.page_height || 1;
        renderPreview(res.preview_urls);
        if (state.wordMap.length > 0) { showHighlightBar(); } else { hideHighlightBar(); }
        var expBtn = getEl("btn-export");
        if (expBtn) expBtn.disabled = false;
        statusMsg("Fertig — " + res.pages + " Seite(n).", "ok");
      })
      .catch(function (e) { statusMsg("Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  function renderPreview(urls) {
    var el = getEl("preview");
    if (!el) return;
    if (!urls || !urls.length) {
      el.innerHTML = '<div class="empty-state-nice"><p>Keine Seiten.</p></div>';
      return;
    }
    el.innerHTML = urls.map(function (u, i) {
      return '<div class="page-container" data-page="' + i + '"><img src="' + u + '" alt="Seite ' + (i + 1) + '" /></div>';
    }).join("");

    if (state.wordMap.length > 0 && state.pageWidth > 0) {
      qa(".page-container", el).forEach(function (container) {
        var pageIdx = parseInt(container.getAttribute("data-page"), 10);
        buildWordOverlays(container, pageIdx);
      });
    }
  }

  function buildWordOverlays(container, pageIdx) {
    for (var i = 0; i < state.wordMap.length; i++) {
      var wb = state.wordMap[i];
      if (wb.page !== pageIdx) continue;
      var div = document.createElement("div");
      div.className = "word-overlay";
      div.setAttribute("data-word-idx", String(i));
      div.style.left = (wb.x / state.pageWidth * 100).toFixed(3) + "%";
      div.style.top = (wb.y / state.pageHeight * 100).toFixed(3) + "%";
      div.style.width = (wb.w / state.pageWidth * 100).toFixed(3) + "%";
      div.style.height = (wb.h / state.pageHeight * 100).toFixed(3) + "%";
      div.addEventListener("click", onWordClick);
      container.appendChild(div);
    }
  }

  function doExport(fmt) {
    if (!state.projectId) return;
    var btn = getEl("btn-export");
    var reset = showSpinner(btn, "…");
    var pre = getHighlightList().length > 0
      ? applyHighlightsToServer().catch(function () {})
      : Promise.resolve();
    pre.then(function () {
      return API.exportHandwriting(state.projectId, fmt);
    }).then(function (res) {
      var dlUrl = "/api/handwriting/export/download/" + encodeURIComponent(res.filename);
      window.location.href = dlUrl;
      statusMsg("Export fertig.", "ok");
      scheduleServerHighlight();
    }).catch(function (e) {
      statusMsg("Export: " + e.message, "err");
    }).finally(function () { reset(); });
  }

  // ---- Utils ----
  function fmtScale(v) { return Number(v).toFixed(2).replace(/0$/, "") + "×"; }
})();
