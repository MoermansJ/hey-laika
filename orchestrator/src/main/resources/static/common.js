/* Shared helpers for every console page (loaded before each page's own
 * script). Plain globals on purpose: the pages are classic scripts.
 *
 *  esc(text)                      HTML-escape server / LLM / user strings
 *  hlRobotParam(fallback)         ?robot=<id> from the URL (embedded tabs)
 *  hlFetchJson(url, opts, ms)     fetch + JSON with an AbortController timeout
 *  hlApi(base, path, opts)        hlFetchJson that throws {message,status}
 *  hlPoll(fn, intervalMs)         overlap-guarded interval that pauses while
 *                                 the tab is hidden or the parent says so
 *  hlToast(message, isError)      toast that works with either markup style
 */
"use strict";

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function hlRobotParam(fallback) {
  return new URLSearchParams(location.search).get("robot") || fallback;
}

const HL_FETCH_TIMEOUT_MS = 8000;

async function hlFetchJson(url, options = {}, timeoutMs = HL_FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const body = await res.json().catch(() => null);
    return { res, body };
  } finally {
    clearTimeout(timer);
  }
}

async function hlApi(base, path, options) {
  const { res, body } = await hlFetchJson(`${base}${path}`, options);
  if (!res.ok) {
    const message = body?.message || body?.error || `HTTP ${res.status}`;
    throw Object.assign(new Error(message), { status: res.status, body });
  }
  return body;
}

// Visibility: a page polls only while its document is visible AND, when
// embedded as a robot-page tab, while the parent reports it as the active
// tab (the parent posts {type:"laika-visible", visible}).
const hlVisibility = { parentVisible: true };
window.addEventListener("message", (event) => {
  const data = event.data;
  if (data && data.type === "laika-visible") {
    hlVisibility.parentVisible = !!data.visible;
  }
});

function hlVisible() {
  return !document.hidden && hlVisibility.parentVisible;
}

function hlPoll(fn, intervalMs, { immediate = true } = {}) {
  let inFlight = false;
  let stopped = false;
  const tick = async () => {
    if (stopped || inFlight || !hlVisible()) return;
    inFlight = true;
    try { await fn(); } catch { /* fn owns its error UI */ }
    finally { inFlight = false; }
  };
  const timer = setInterval(tick, intervalMs);
  if (immediate) tick();
  // Catch up as soon as the page becomes visible again.
  document.addEventListener("visibilitychange", () => { if (hlVisible()) tick(); });
  window.addEventListener("message", (e) => {
    if (e.data && e.data.type === "laika-visible" && e.data.visible) tick();
  });
  return { stop() { stopped = true; clearInterval(timer); }, tick };
}

function hlToast(message, isError) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.textContent = message;
  // index.html styles .toast via .hidden/.error; the sub-pages use
  // #toast with inline display and an .err class. Serve both.
  el.classList.toggle("error", !!isError);
  el.classList.toggle("err", !!isError);
  el.classList.remove("hidden");
  el.style.display = "block";
  clearTimeout(el._timer);
  el._timer = setTimeout(() => {
    el.classList.add("hidden");
    el.style.display = "none";
  }, 3500);
}

// Retry affordance for pages whose first fetch fails (adapter down).
function hlRetryBlock(container, message, retry) {
  container.innerHTML = `<span class="hint">${esc(message)}</span> ` +
      `<button type="button" class="hl-retry">Retry</button>`;
  container.querySelector(".hl-retry").onclick = retry;
}
