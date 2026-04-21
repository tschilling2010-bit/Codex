// Shared UI helpers
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }

function setStatus(el, message, kind = "") {
  if (!el) return;
  el.className = "status " + kind;
  el.textContent = message || "";
}

function showSpinner(btn, label = "Lädt…") {
  if (!btn) return () => {};
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> ${label}`;
  return () => { btn.disabled = false; btn.innerHTML = original; };
}

function formatDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function fmtBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n > 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function highlightNav() {
  const path = location.pathname;
  $$(".nav-links a").forEach(a => {
    const href = a.getAttribute("href");
    const match =
      (href === "/" && (path === "/" || path === "/handwriting.html")) ||
      (href !== "/" && path.startsWith(href));
    if (match) a.classList.add("active");
  });
}

document.addEventListener("DOMContentLoaded", highlightNav);
