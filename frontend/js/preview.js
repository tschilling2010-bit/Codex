(async function () {
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  const els = {
    title: $("#title"),
    subtitle: $("#subtitle"),
    preview: $("#preview"),
    status: $("#status"),
    btnPdf: $("#btn-pdf"),
    btnPng: $("#btn-png"),
    btnJpg: $("#btn-jpg"),
  };

  if (!id) { setStatus(els.status, "Kein Projekt angegeben.", "err"); return; }

  let project = null;
  try {
    project = await API.getProject(id);
    els.title.textContent = project.title;
    els.subtitle.textContent =
      `${project.kind === "handwriting" ? "Handschrift" : "Hefter"} · ${project.pages} Seite(n) · ${formatDate(project.created_at)}`;
    const urls = [];
    for (let i = 1; i <= project.pages; i++) {
      urls.push(`/api/projects/${id}/pages/${i}`);
    }
    if (urls.length) {
      els.preview.innerHTML = urls.map(u =>
        `<div class="page-shadow"><img src="${u}" /></div>`
      ).join("");
    } else {
      els.preview.innerHTML = `<div class="empty-state">Keine Seiten vorhanden.</div>`;
    }
  } catch (e) {
    setStatus(els.status, "Projekt konnte nicht geladen werden: " + e.message, "err");
    return;
  }

  async function exportFormat(fmt) {
    const btn = { pdf: els.btnPdf, png: els.btnPng, jpg: els.btnJpg }[fmt];
    const reset = showSpinner(btn, fmt.toUpperCase());
    try {
      const api = project.kind === "handwriting" ? API.exportHandwriting : API.exportHefter;
      const res = await api(id, fmt);
      window.open(res.url, "_blank");
      setStatus(els.status, "Export fertig.", "ok");
    } catch (e) {
      setStatus(els.status, "Export fehlgeschlagen: " + e.message, "err");
    } finally { reset(); }
  }
  els.btnPdf.addEventListener("click", () => exportFormat("pdf"));
  els.btnPng.addEventListener("click", () => exportFormat("png"));
  els.btnJpg.addEventListener("click", () => exportFormat("jpg"));
})();
