// Shared UI helpers – ES5-safe
function setStatus(el, message, kind) {
  if (!el) return;
  el.className = "status " + (kind || "");
  el.textContent = message || "";
}

function showSpinner(btn, label) {
  if (!btn) return function () {};
  var original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> ' + (label || "Lädt…");
  return function () { btn.disabled = false; btn.innerHTML = original; };
}

function formatDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function fmtBytes(n) {
  if (!n) return "0 B";
  var units = ["B", "KB", "MB", "GB"];
  var i = 0;
  while (n > 1024 && i < units.length - 1) { n /= 1024; i++; }
  return (n < 10 ? n.toFixed(1) : n.toFixed(0)) + " " + units[i];
}

function escapeHtml(s) {
  var map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(s).replace(/[&<>"']/g, function (c) { return map[c]; });
}

function highlightNav() {
  var path = location.pathname;
  var links = document.querySelectorAll(".nav-links a");
  for (var i = 0; i < links.length; i++) {
    var a = links[i];
    var href = a.getAttribute("href");
    var match =
      (href === "/" && (path === "/" || path === "/handwriting.html")) ||
      (href !== "/" && path.indexOf(href) === 0);
    if (match) a.classList.add("active");
  }
}

document.addEventListener("DOMContentLoaded", highlightNav);
