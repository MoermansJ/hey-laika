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
 *  hlMountClock(container)        live "now" next to a page's timestamps
 *                                 (auto-mounted into .topbar on load)
 *  hlLoadBadgePalette(base)       fetch the adapter's mood palette + badge enum
 *  hlBadge(kind, label)           a badge coloured like the LED mood it stands for
 *  hlPage(opts)                   fleet fetch + robot resolution + the robot
 *                                 selector (removed when embedded in a tab)
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


// ---- clock: every page that shows timestamps also shows "now" ----
function hlMountClock(container) {
  const el = document.createElement("span");
  el.className = "chip hl-clock";
  el.title = "This browser's clock, to compare with the timestamps on this page";
  el.style.marginLeft = "auto";
  const tick = () => { el.textContent = new Date().toLocaleTimeString(); };
  tick();
  setInterval(tick, 1000);
  container.appendChild(el);
  return el;
}
document.addEventListener("DOMContentLoaded", () => {
  const bar = document.querySelector(".topbar");
  if (bar && !bar.querySelector(".hl-clock")) hlMountClock(bar);
});

// ---- badges share the LED palette ----
// The adapter's /mood answers with `palette` (mood -> r,g,b,effect) and
// `badges` (badge kind -> mood). A badge on screen and the LED on the head
// therefore always agree; the fallback below only covers an unreachable
// adapter and mirrors dog/app/mood.py.
const hlBadgeState = { palette: null, badges: null };
const HL_BADGE_FALLBACK = {
  wake:      { r: 0, g: 255, b: 40, effect: "solid" },
  wakeGreet: { r: 0, g: 255, b: 40, effect: "pulse" },
  person:    { r: 0, g: 210, b: 255, effect: "solid" },
  online:    { r: 0, g: 255, b: 40, effect: "solid" },
};

async function hlLoadBadgePalette(base) {
  try {
    const mood = await hlApi(base, "/mood");
    hlBadgeState.palette = mood.palette || null;
    hlBadgeState.badges = mood.badges || null;
  } catch { /* fallback palette stays */ }
}

function hlBadge(kind, label) {
  const mood = hlBadgeState.badges?.[kind];
  const spec = (mood && hlBadgeState.palette?.[mood]) || HL_BADGE_FALLBACK[kind]
      || { r: 127, g: 140, b: 141, effect: "solid" };
  const pulse = spec.effect === "pulse" ? " hl-pulse" : "";
  return `<span class="hl-badge${pulse}" style="--hl-badge:rgb(${spec.r},${spec.g},${spec.b})"` +
      ` title="LED mood: ${esc(mood || kind)}">${esc(label ?? kind)}</span>`;
}

// ---- page boot: every sub-page starts the same way ----
// Fetches the fleet, resolves the robot from ?robot= (the parent tab names
// it) or the first robot, fills the #robot-select when the page stands
// alone and removes it when embedded (the robot header already says who).
async function hlPage({ onRobotChange } = {}) {
  const embedded = new URLSearchParams(location.search).has("embedded");
  const robots = await hlApi("", "/api/fleet/robots");
  const wanted = hlRobotParam(null);
  const robotId = robots.some((r) => r.robotId === wanted) ? wanted : robots[0]?.robotId;
  const select = document.getElementById("robot-select");
  if (select) {
    if (embedded) {
      select.remove();
    } else {
      select.innerHTML = robots.map((r) =>
          `<option value="${esc(r.robotId)}">${esc(r.name)}</option>`).join("");
      select.value = robotId ?? "";
      select.onchange = (e) => onRobotChange?.(e.target.value);
    }
  }
  const name = robots.find((r) => r.robotId === robotId)?.name;
  if (!embedded && name) {
    const h1 = document.querySelector("h1");
    if (h1 && !h1.dataset.named) { h1.dataset.named = "1"; h1.textContent += ` — ${name}`; }
  }
  return { robots, robotId, embedded, base: `/api/robots/${robotId}` };
}
