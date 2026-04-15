(async function () {
  const list = $("#projects");
  try {
    const projects = await API.listProjects();
    if (!projects.length) {
      list.innerHTML = `<div class="empty-state">Noch keine Projekte. Starte eines der beiden Module oben.</div>`;
      return;
    }
    list.innerHTML = `
      <table class="table">
        <thead><tr><th>Titel</th><th>Typ</th><th>Seiten</th><th>Erstellt</th><th></th></tr></thead>
        <tbody>
          ${projects.slice(0, 8).map(p => `
            <tr>
              <td>${escapeHtml(p.title)}</td>
              <td>${p.kind === "handwriting" ? "Handschrift" : "Hefter"}</td>
              <td>${p.pages}</td>
              <td>${formatDate(p.created_at)}</td>
              <td style="text-align:right">
                <a class="btn btn-soft" href="/preview.html?id=${p.id}">Öffnen</a>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>`;
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Projekte konnten nicht geladen werden: ${e.message}</div>`;
  }
})();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
