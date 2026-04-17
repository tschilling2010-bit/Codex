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
          <h3 style="margin:0; font-size:17px">${escapeHtml(p.title)}</h3>
          <span class="muted" style="margin-left:8px; font-size:13px">${p.kind === "handwriting" ? "Handschrift" : "Hefterblatt"} · ${formatDate(p.created_at)}</span>
          <div class="toolbar-spacer"></div>
          <button class="btn btn-ghost" onclick="deleteProject('${p.id}', this)" style="font-size:13px; padding:8px 14px">Löschen</button>
        </div>
        ${exportRows
          ? `<table class="table"><thead><tr><th>Datei</th><th>Format</th><th></th></tr></thead><tbody>${exportRows}</tbody></table>`
          : `<div class="muted" style="font-size:14px">Noch keine Exporte. Öffne das Projekt erneut zum Exportieren.</div>`}
      </section>`;
    }).join("");
  } catch (e) {
    root.innerHTML = `<div class="empty-state">Fehler: ${escapeHtml(e.message)}</div>`;
  }
})();

async function deleteProject(id, btn) {
  if (!confirm("Projekt wirklich löschen?")) return;
  try {
    await API.deleteProject(id);
    btn.closest("section").remove();
  } catch (e) {
    alert("Löschen fehlgeschlagen: " + e.message);
  }
}
