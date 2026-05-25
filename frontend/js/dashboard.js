(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var list = document.getElementById("projects");
    API.listProjects().then(function (projects) {
      if (!list) return;
      if (!projects || projects.length === 0) {
        list.innerHTML = '<div class="empty-state">Noch keine Projekte. Starte mit einer der Funktionen oben.</div>';
        return;
      }
      var rows = projects.slice(0, 8).map(function (p) {
        return "<tr><td>" + escapeHtml(p.title || "Ohne Titel") + "</td>" +
          "<td>" + (p.kind === "handwriting" ? "Handschrift" : "Hefterblatt") + "</td>" +
          "<td>" + (p.pages || "—") + "</td>" +
          "<td>" + formatDate(p.created_at) + "</td></tr>";
      });
      list.innerHTML = '<table class="table"><thead><tr>' +
        '<th>Titel</th><th>Typ</th><th>Seiten</th><th>Erstellt</th>' +
        '</tr></thead><tbody>' + rows.join("") + "</tbody></table>";
    }).catch(function () {
      if (list) list.innerHTML = '<div class="empty-state">Projekte konnten nicht geladen werden.</div>';
    });
  });
})();
