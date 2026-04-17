(async function () {
  const list = $("#projects");
  try {
    const projects = await API.listProjects();
    if (!projects.length) {
      list.innerHTML = `<div class="empty-state">Noch keine Projekte. Starte mit einer der Funktionen oben.</div>`;
      return;
    }
    list.innerHTML = `
      <table class="table">
        <thead><tr><th>Titel</th><th>Typ</th><th>Seiten</th><th>Erstellt</th></tr></thead>
        <tbody>
          ${projects.slice(0, 8).map(p => `
            <tr>
              <td>${escapeHtml(p.title)}</td>
              <td>${p.kind === "handwriting" ? "Handschrift" : "Hefterblatt"}</td>
              <td>${p.pages}</td>
              <td>${formatDate(p.created_at)}</td>
            </tr>`).join("")}
        </tbody>
      </table>`;
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Projekte konnten nicht geladen werden.</div>`;
  }
})();
