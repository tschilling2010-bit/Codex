(async function () {
  const els = {
    profile: $("#default-profile"),
    sheet: $("#default-sheet"),
    format: $("#default-format"),
    margin: $("#margin"),
    line: $("#line"),
    glyph: $("#glyph"),
    ink: $("#ink"),
    save: $("#save"),
    status: $("#status"),
    profiles: $("#profiles"),
  };

  async function reloadProfiles(selected) {
    const profiles = await API.listProfiles();
    els.profile.innerHTML = profiles.map(p =>
      `<option value="${p.id}">${p.name}${p.source === "default" ? " · Standard" : ""}</option>`
    ).join("");
    if (selected && profiles.some(p => p.id === selected)) els.profile.value = selected;

    els.profiles.innerHTML = profiles.length ? `
      <table class="table">
        <thead><tr><th>Name</th><th>Typ</th><th>Glyphen</th><th></th></tr></thead>
        <tbody>${profiles.map(p => `
          <tr>
            <td>${escapeHtml(p.name)}</td>
            <td>${p.source === "default" ? "Standard" : "Eigen"}</td>
            <td>${p.glyph_count}</td>
            <td style="text-align:right">
              ${p.source === "default"
                ? `<span class="muted" style="font-size:13px">geschützt</span>`
                : `<button class="btn btn-ghost" data-delete="${p.id}">Löschen</button>`}
            </td>
          </tr>`).join("")}
        </tbody>
      </table>` : `<div class="empty-state">Keine Profile vorhanden.</div>`;

    els.profiles.querySelectorAll("[data-delete]").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Profil wirklich löschen?")) return;
        try {
          await API.deleteProfile(btn.dataset.delete);
          await reloadProfiles(els.profile.value);
        } catch (e) {
          setStatus(els.status, "Löschen fehlgeschlagen: " + e.message, "err");
        }
      });
    });
  }

  const settings = await API.getSettings();
  els.sheet.value = settings.default_sheet_type;
  els.format.value = settings.default_export_format;
  els.margin.value = settings.margin_mm;
  els.line.value = settings.line_height_mm;
  els.glyph.value = settings.glyph_height_mm;
  els.ink.value = settings.ink_color;
  await reloadProfiles(settings.default_profile_id);

  els.save.addEventListener("click", async () => {
    const reset = showSpinner(els.save, "Speichere…");
    try {
      const payload = {
        default_profile_id: els.profile.value,
        default_sheet_type: els.sheet.value,
        default_export_format: els.format.value,
        margin_mm: parseFloat(els.margin.value),
        line_height_mm: parseFloat(els.line.value),
        glyph_height_mm: parseFloat(els.glyph.value),
        ink_color: els.ink.value,
      };
      await API.saveSettings(payload);
      setStatus(els.status, "Gespeichert.", "ok");
    } catch (e) {
      setStatus(els.status, "Fehler: " + e.message, "err");
    } finally { reset(); }
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
