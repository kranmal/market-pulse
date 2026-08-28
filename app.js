(() => {
"use strict";

const LS_THEME = "mp.theme";
const REFRESH_MS = 5 * 60 * 1000; // re-poll data/news.json client-side every 5 min

const $ = (s) => document.querySelector(s);

const state = {
  items: [],
  generatedAt: null,
  cat: "all",
  q: "",
};

/* ── Theme ── */
function effectiveDark() {
  const stored = localStorage.getItem(LS_THEME);
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function applyTheme() {
  const dark = effectiveDark();
  const stored = localStorage.getItem(LS_THEME);
  if (stored === "light") document.documentElement.setAttribute("data-theme", "light");
  else if (stored === "dark") document.documentElement.setAttribute("data-theme", "dark");
  else document.documentElement.removeAttribute("data-theme");
  $("#themeBtn").setAttribute("aria-pressed", String(dark));
}
$("#themeBtn").addEventListener("click", () => {
  const nowDark = effectiveDark();
  try { localStorage.setItem(LS_THEME, nowDark ? "light" : "dark"); } catch {}
  applyTheme();
});
applyTheme();

/* ── Time formatting ── */
function timeAgo(iso) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Math.max(0, Date.now() - t);
  const min = Math.round(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

/* ── Rendering ── */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function matchesFilters(item) {
  if (state.cat !== "all" && item.category !== state.cat) return false;
  if (state.q) {
    const hay = `${item.title} ${item.source} ${item.region}`.toLowerCase();
    if (!hay.includes(state.q)) return false;
  }
  return true;
}

function render() {
  const list = $("#list");
  const empty = $("#empty");
  const filtered = state.items.filter(matchesFilters);

  if (filtered.length === 0) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  list.innerHTML = filtered.map((item) => `
    <a class="item" href="${escapeHtml(item.link)}" target="_blank" rel="noopener noreferrer">
      <div class="item-top">
        <span class="badge ${item.category === "crypto" ? "crypto" : "stocks"}">${item.category}</span>
        <span class="region">${escapeHtml(item.region || "")}</span>
      </div>
      <p class="item-title">${escapeHtml(item.title)}</p>
      <div class="item-meta"><span class="src">${escapeHtml(item.source)}</span> · ${timeAgo(item.published)}</div>
    </a>
  `).join("");
}

function setStatus(text, warn) {
  const el = $("#status");
  el.classList.toggle("warn", !!warn);
  el.innerHTML = `<span class="dot"></span>${escapeHtml(text)}`;
}

async function loadData() {
  setStatus("Loading…");
  try {
    const res = await fetch(`data/news.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.items = Array.isArray(data.items) ? data.items : [];
    state.generatedAt = data.generated_at || null;
    setStatus(state.generatedAt ? `Updated ${timeAgo(state.generatedAt)}` : `${state.items.length} stories`);
    render();
  } catch (e) {
    setStatus("Couldn't load news feed", true);
    console.error(e);
  }
}

/* ── Controls ── */
$("#catSeg").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-cat]");
  if (!btn) return;
  state.cat = btn.dataset.cat;
  $$("#catSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  render();
});
function $$(s) { return Array.from(document.querySelectorAll(s)); }

let qTimer = null;
$("#q").addEventListener("input", (e) => {
  clearTimeout(qTimer);
  const val = e.target.value;
  qTimer = setTimeout(() => {
    state.q = val.trim().toLowerCase();
    render();
  }, 120);
});

$("#refreshBtn").addEventListener("click", loadData);

loadData();
setInterval(loadData, REFRESH_MS);
})();
