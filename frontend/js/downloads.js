(async function () {
  const root = $("#projects");
  try {
    const projects = await API.listProjects();
    if (!projects.length) {
      root.innerHTML = `<div class="empty-state">Noch keine Exporte. Erstelle zuerst ein Projekt.</div>`;
      return;
    }
    root.innerHTML = projects.map(p => {
      const exportRows = (p.exports || []).map(url => {
        const name = url.split("/").pop();
        const fmt = (name.split(".").pop() || "").toUpperCase();
        return `<tr>
          <td>${escapeHtml(name)}</td>
          <td>${fmt}</td>
          <td style="text-align:right"><a class="btn btn-soft" href="${url}" target="_blank">Herunterladen</a></td>
        </tr>`;
      }).join("");
      return `
      <section style="margin-bottom:28px">
        <div class="toolbar" style="margin-bottom:10px">
          <h3 style="margin:0">${escapeHtml(p.title)}</h3>
          <span class="muted" style="margin-left:8px">${p.kind === "handwriting" ? "Handschrift" : "Hefter"} · ${formatDate(p.created_at)}</span>
          <div class="toolbar-spacer"></div>
          <a class="btn btn-soft" href="/preview.html?id=${p.id}">Vorschau</a>
        </div>
        ${exportRows
          ? `<table class="table"><thead><tr><th>Datei</th><th>Format</th><th></th></tr></thead><tbody>${exportRows}</tbody></table>`
          : `<div class="muted" style="font-size:14px">Noch keine Exporte für dieses Projekt.</div>`}
      </section>`;
    }).join("");
  } catch (e) {
    root.innerHTML = `<div class="empty-state">Fehler: ${e.message}</div>`;
  }
})();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
