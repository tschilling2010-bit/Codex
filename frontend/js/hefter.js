(function () {
  "use strict";

  var state = { subjects: [], activeId: null, subject: null };
  var selectedFiles = [];

  function getEl(id) { return document.getElementById(id); }
  function qa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function on(el, evt, fn) { if (el) el.addEventListener(evt, fn); }

  // ---- Init ----
  document.addEventListener("DOMContentLoaded", function () {
    try { bindUI(); } catch (e) { console.error("bindUI error:", e); }
    checkAi();
    loadSubjects().catch(function (e) { console.error("loadSubjects error:", e); });
  });

  function checkAi() {
    API.hefterStatus().then(function (s) {
      var el = getEl("ai-warning");
      if (el) el.style.display = s.ai_configured ? "none" : "";
    }).catch(function () {});
  }

  // ---- Views ----
  function showList() {
    state.activeId = null;
    state.subject = null;
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "";
    if (vd) vd.style.display = "none";
    hideNewSubjectForm();
  }
  function showDetail() {
    var vl = getEl("view-list"), vd = getEl("view-detail");
    if (vl) vl.style.display = "none";
    if (vd) vd.style.display = "";
  }

  // ---- Subjects list ----
  function loadSubjects() {
    var grid = getEl("subject-grid");
    return API.listSubjects().then(function (list) {
      state.subjects = list;
      renderSubjectGrid();
    }).catch(function (e) {
      if (grid) grid.innerHTML = '<p class="muted">Fehler beim Laden: ' + escapeHtml(e.message) + "</p>";
    });
  }

  function renderSubjectGrid() {
    var grid = getEl("subject-grid");
    if (!grid) return;
    if (state.subjects.length === 0) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Noch keine Fächer. Lege dein erstes an!</div>';
      return;
    }
    grid.innerHTML = state.subjects.map(function (s) {
      return '<a class="card interactive" data-id="' + s.id + '" href="#" style="border-top:6px solid ' + escapeHtml(s.color) + '">' +
        '<h3>' + escapeHtml(s.name) + '</h3>' +
        '<p>' + s.page_count + ' Seite(n) &middot; ' + paperLabel(s.paper_type) + '</p></a>';
    }).join("");
    qa(".card.interactive", grid).forEach(function (card) {
      card.addEventListener("click", function (e) {
        e.preventDefault();
        openSubject(card.getAttribute("data-id"));
      });
    });
  }

  function paperLabel(p) {
    return p === "kariert" ? "Kariert" : (p === "blanko" ? "Blanko" : "Liniert");
  }

  function openSubject(id) {
    state.activeId = id;
    return API.getSubject(id).then(function (s) {
      state.subject = s;
      showDetail();
      var nameEl = getEl("subject-name");
      if (nameEl) nameEl.value = s.name;
      var col = getEl("s-color"); if (col) col.value = s.color;
      var pap = getEl("s-paper"); if (pap) pap.value = s.paper_type;
      var pdfBtn = getEl("btn-export-pdf");
      if (pdfBtn) pdfBtn.href = API.subjectPdfUrl(id);
      renderPages();
      activateTab("pages");
    }).catch(function (e) {
      alert("Fach konnte nicht geladen werden: " + e.message);
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

  // ---- Pages ----
  function renderPages() {
    var info = getEl("pages-info");
    var grid = getEl("pages-grid");
    var pdfBtn = getEl("btn-export-pdf");
    if (!grid || !state.subject) return;
    var pages = state.subject.pages || [];
    if (info) info.textContent = pages.length === 0 ? "Noch keine Seiten." : (pages.length + " Seite(n) im Hefter");
    if (pdfBtn) pdfBtn.style.display = pages.length === 0 ? "none" : "";
    if (pages.length === 0) {
      grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Erstelle deine erste Seite im Tab „Neue Seite".</div>';
      return;
    }
    grid.innerHTML = pages.map(function (p, i) {
      return '<div class="page-shadow" data-page="' + p.id + '" style="cursor:pointer; position:relative">' +
        '<img src="' + escapeHtml(p.image_url) + '" alt="Seite ' + (i + 1) + '" />' +
        '<div style="position:absolute; bottom:0; left:0; right:0; padding:10px 14px; background:rgba(255,255,255,0.92); font-size:13px; font-weight:600">' +
        escapeHtml(p.title) + '</div></div>';
    }).join("");
    qa(".page-shadow[data-page]", grid).forEach(function (card) {
      card.addEventListener("click", function () { openLightbox(card.getAttribute("data-page")); });
    });
  }

  // ---- Lightbox ----
  function openLightbox(pageId) {
    var pages = state.subject ? (state.subject.pages || []) : [];
    var page = null;
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].id === pageId) { page = pages[i]; break; }
    }
    if (!page) return;
    var box = getEl("lightbox");
    var img = getEl("lightbox-img");
    var dl = getEl("lightbox-download");
    if (img) img.src = page.image_url;
    if (dl) {
      dl.href = page.image_url;
      var safe = (page.title || "Seite").replace(/[^a-zA-Z0-9_-]/g, "_");
      dl.setAttribute("download", safe + ".png");
    }
    if (box) {
      box.style.display = "flex";
      box.setAttribute("data-page", pageId);
    }
  }
  function closeLightbox() {
    var box = getEl("lightbox");
    if (box) box.style.display = "none";
  }

  // ---- File upload ----
  function bindFileUpload() {
    var drop = getEl("file-drop");
    var input = getEl("file-input");
    if (!drop || !input) return;

    on(drop, "click", function () { input.click(); });

    on(input, "change", function () {
      addFiles(input.files);
      input.value = "";
    });

    on(drop, "dragover", function (e) {
      e.preventDefault();
      drop.style.borderColor = "var(--primary)";
    });
    on(drop, "dragleave", function () {
      drop.style.borderColor = "var(--border)";
    });
    on(drop, "drop", function (e) {
      e.preventDefault();
      drop.style.borderColor = "var(--border)";
      addFiles(e.dataTransfer.files);
    });
  }

  function addFiles(fileList) {
    for (var i = 0; i < fileList.length; i++) {
      selectedFiles.push(fileList[i]);
    }
    renderFileList();
  }

  function renderFileList() {
    var el = getEl("file-list");
    if (!el) return;
    if (selectedFiles.length === 0) { el.innerHTML = ""; return; }
    el.innerHTML = selectedFiles.map(function (f, i) {
      var size = f.size < 1024 ? f.size + " B" : (f.size / 1024).toFixed(0) + " KB";
      var tag = (f.type === "application/pdf") ? "[PDF]" : "[Bild]";
      return '<div style="display:flex; align-items:center; gap:8px; padding:6px 0; font-size:14px">' +
        '<span class="muted">' + tag + '</span>' +
        '<span style="flex:1">' + escapeHtml(f.name) + ' <span class="muted">(' + size + ')</span></span>' +
        '<button class="btn btn-ghost btn-rm-file" data-idx="' + i + '" style="padding:4px 10px; font-size:12px; color:var(--err)">Entfernen</button>' +
        '</div>';
    }).join("");
    qa(".btn-rm-file", el).forEach(function (btn) {
      btn.addEventListener("click", function () {
        selectedFiles.splice(parseInt(btn.getAttribute("data-idx"), 10), 1);
        renderFileList();
      });
    });
  }

  // ---- Generate page ----
  function generatePage() {
    if (!state.activeId) return;
    var titleEl = getEl("page-title");
    var contentEl = getEl("page-content");
    var content = contentEl ? contentEl.value.trim() : "";
    if (!content && selectedFiles.length === 0) {
      msg(getEl("gen-status"), "Bitte Inhalt eingeben oder Dateien hochladen.", "err");
      return;
    }
    var btn = getEl("btn-generate");
    var reset = showSpinner(btn, "Erzeuge…");
    var info = selectedFiles.length > 0
      ? "KI analysiert Dateien und gestaltet die Seite…"
      : "KI gestaltet die Seite, das dauert einen Moment…";
    msg(getEl("gen-status"), info);
    API.createHefterPage(state.activeId, content, titleEl ? titleEl.value : "", selectedFiles)
      .then(function () {
        msg(getEl("gen-status"), "Seite fertig!", "ok");
        if (titleEl) titleEl.value = "";
        if (contentEl) contentEl.value = "";
        selectedFiles = [];
        renderFileList();
        return API.getSubject(state.activeId);
      })
      .then(function (s) {
        if (s) {
          state.subject = s;
          renderPages();
          activateTab("pages");
        }
      })
      .catch(function (e) { msg(getEl("gen-status"), "Fehler: " + e.message, "err"); })
      .finally(function () { reset(); });
  }

  // ---- New subject form ----
  function showNewSubjectForm() {
    var form = getEl("new-subject-form");
    var btn = getEl("btn-new-subject");
    if (form) form.style.display = "";
    if (btn) btn.style.display = "none";
    var n = getEl("ns-name");
    if (n) { n.value = ""; n.focus(); }
  }
  function hideNewSubjectForm() {
    var form = getEl("new-subject-form");
    var btn = getEl("btn-new-subject");
    if (form) form.style.display = "none";
    if (btn) btn.style.display = "";
  }
  function submitNewSubject() {
    var n = getEl("ns-name");
    var c = getEl("ns-color");
    var p = getEl("ns-paper");
    var name = n ? n.value.trim() : "";
    if (!name) return;
    var data = {
      name: name,
      color: c ? c.value : "#1a6c8a",
      paper_type: p ? p.value : "liniert"
    };
    API.createSubject(data).then(function (s) {
      hideNewSubjectForm();
      return loadSubjects().then(function () { return openSubject(s.id); });
    }).catch(function (e) { alert("Fehler: " + e.message); });
  }

  // ---- Auto-save settings ----
  var saveNameTimer, saveSettingsTimer;
  function autoSaveName() {
    clearTimeout(saveNameTimer);
    saveNameTimer = setTimeout(function () {
      var el = getEl("subject-name");
      var name = el ? el.value.trim() : "";
      if (!name || !state.activeId) return;
      API.updateSubject(state.activeId, { name: name })
        .then(function (s) { state.subject = s; }).catch(function () {});
    }, 600);
  }
  function autoSaveSettings() {
    clearTimeout(saveSettingsTimer);
    saveSettingsTimer = setTimeout(function () {
      if (!state.activeId) return;
      var c = getEl("s-color"), p = getEl("s-paper");
      var data = {};
      if (c) data.color = c.value;
      if (p) data.paper_type = p.value;
      API.updateSubject(state.activeId, data)
        .then(function (s) { state.subject = s; }).catch(function () {});
    }, 400);
  }

  // ---- Bind UI ----
  function bindUI() {
    on(getEl("btn-new-subject"), "click", showNewSubjectForm);
    on(getEl("btn-ns-cancel"), "click", hideNewSubjectForm);
    on(getEl("btn-ns-confirm"), "click", submitNewSubject);
    on(getEl("ns-name"), "keydown", function (e) {
      if (e.key === "Enter" || e.keyCode === 13) { e.preventDefault(); submitNewSubject(); }
    });

    on(getEl("btn-back"), "click", function () { loadSubjects().then(showList); });

    on(getEl("btn-delete-subject"), "click", function () {
      if (!state.activeId) return;
      var name = state.subject ? state.subject.name : "Fach";
      if (!confirm(name + " mit allen Seiten wirklich löschen?")) return;
      API.deleteSubject(state.activeId).catch(function () {})
        .then(function () { return loadSubjects(); })
        .then(showList);
    });

    on(getEl("subject-name"), "input", autoSaveName);
    on(getEl("s-color"), "input", autoSaveSettings);
    on(getEl("s-paper"), "change", autoSaveSettings);

    qa(".tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { activateTab(btn.getAttribute("data-tab")); });
    });

    on(getEl("btn-generate"), "click", generatePage);
    bindFileUpload();

    on(getEl("lightbox-close"), "click", closeLightbox);
    on(getEl("lightbox"), "click", function (e) {
      if (e.target && e.target.id === "lightbox") closeLightbox();
    });
    on(getEl("lightbox-delete"), "click", function () {
      var box = getEl("lightbox");
      var pid = box ? box.getAttribute("data-page") : "";
      if (!pid || !state.activeId) return;
      if (!confirm("Diese Seite wirklich löschen?")) return;
      API.deleteHefterPage(state.activeId, pid)
        .then(function () { return API.getSubject(state.activeId); })
        .then(function (s) { state.subject = s; renderPages(); closeLightbox(); })
        .catch(function (e) { alert("Fehler: " + e.message); });
    });
  }

  function msg(el, text, kind) {
    setStatus(el, text, kind);
    if (el) el.style.display = text ? "" : "none";
  }
})();
