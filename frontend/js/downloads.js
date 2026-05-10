(function () {
  "use strict";

  function getEl(id) { return document.getElementById(id); }

  document.addEventListener("DOMContentLoaded", function () {
    var root = getEl("projects");
    if (!root) return;
    API.listProjects().then(function (projects) {
      if (!projects.length) {
        root.innerHTML = '<div class="empty-state">Noch keine Exporte. Erstelle zuerst ein Projekt.</div>';
        return;
      }
      root.innerHTML = projects.map(function (p) {
        var exportRows = (p.exports || []).map(function (url) {
          var name = url.split("/").pop();
          var fmt = (name.split(".").pop() || "").toUpperCase();
          return '<tr>' +
            '<td>' + escapeHtml(name) + '</td>' +
            '<td>' + fmt + '</td>' +
            '<td style="text-align:right"><a class="btn btn-soft" href="' + url + '" target="_blank">Herunterladen</a></td>' +
            '</tr>';
        }).join("");
        var kindLabel = p.kind === "handwriting" ? "Handschrift" : "Hefterblatt";
        return '<section data-id="' + p.id + '" style="margin-bottom:28px">' +
          '<div class="toolbar" style="margin-bottom:10px">' +
          '<h3 style="margin:0; font-size:17px">' + escapeHtml(p.title) + '</h3>' +
          '<span class="muted" style="margin-left:8px; font-size:13px">' + kindLabel + ' · ' + formatDate(p.created_at) + '</span>' +
          '<div class="toolbar-spacer"></div>' +
          '<button class="btn btn-ghost btn-del" data-id="' + p.id + '" style="font-size:13px; padding:8px 14px">Löschen</button>' +
          '</div>' +
          (exportRows
            ? '<table class="table"><thead><tr><th>Datei</th><th>Format</th><th></th></tr></thead><tbody>' + exportRows + '</tbody></table>'
            : '<div class="muted" style="font-size:14px">Noch keine Exporte. Öffne das Projekt erneut zum Exportieren.</div>') +
          '</section>';
      }).join("");

      Array.prototype.slice.call(root.querySelectorAll(".btn-del")).forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (!confirm("Projekt wirklich löschen?")) return;
          var id = btn.getAttribute("data-id");
          API.deleteProject(id).then(function () {
            var section = btn.closest("section");
            if (section) section.parentNode.removeChild(section);
          }).catch(function (e) { alert("Löschen fehlgeschlagen: " + e.message); });
        });
      });
    }).catch(function (e) {
      root.innerHTML = '<div class="empty-state">Fehler: ' + escapeHtml(e.message) + '</div>';
    });
  });
})();
