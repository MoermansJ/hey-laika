/* Bittle Fleet console.
 *
 * Data flows in through one of two transports feeding handleMessage(topic, body):
 *  - WsTransport: STOMP over WebSocket (push from the orchestrator, primary)
 *  - polling: 4s REST fetch loop, active whenever the WebSocket is down
 * All actions (commands, interactions, animations, autonomous) go through the
 * REST API regardless of transport.
 */
"use strict";

const REFRESH_MS = 4000;
const MAX_WS_FAILURES = 10;

const $ = (sel) => document.querySelector(sel);

const state = {
  page: "dashboard",
  selected: null,          // robotId shown on the robot page
  robots: [],              // RobotInfo[] from /api/fleet/robots
  statuses: {},            // robotId -> RobotStatus
  stats: null,             // FleetStats
  personality: {},         // robotId -> RobotPersonality
  display: {},             // robotId -> DisplayContent
  actions: {},             // robotId -> action-feed entries, newest first
  animations: {},          // robotId -> Animation[]
  mode: {},                // robotId -> operating mode ("stationary"/"roaming"/"fruitfly"/"phone")
  activeTab: "personality",
  wsConnected: false,
  wsGaveUp: false,
  wsFailures: 0,
  arbiterCard: null,       // hlArbiterCard mounted on the Actions tab
  powerCard: null,         // hlPowerCard mounted on the Actions tab
  queueCard: null,         // hlQueueStackCard, moved here from Personality
};

// ---------- helpers ----------

async function api(path, options = {}) {
  const resp = await fetch(path, options);
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(body.message || body.error || `HTTP ${resp.status}`);
  }
  return body;
}

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 3500);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

// URL slug for a robot's page, e.g. "Mocha (mock)" -> "Mocha". Takes
// everything before the first space or parenthesis.
function robotUrlSlug(name) {
  return (name || "").split(/[\s(]/)[0];
}

function fmtUptime(seconds) {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${seconds % 60}s`;
  return `${seconds}s`;
}

function fmtBattery(battery) {
  return battery == null ? "—" : `${Math.round(battery)}%`;
}

function batteryClass(battery) {
  if (battery == null) return "unknown";
  return battery < 20 ? "low" : battery < 50 ? "mid" : "ok";
}

async function runAction(button, action) {
  if (button) button.disabled = true;
  try {
    await action();
  } catch (e) {
    toast(e.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

// ---------- incoming data (both transports call this) ----------

function handleMessage(topic, body) {
  if (topic === "/topic/fleet/status") {
    state.statuses = body;
    onStatusesChanged();
  } else if (topic === "/topic/fleet/stats") {
    state.stats = body;
  } else {
    const m = topic.match(/^\/topic\/robot\/([^/]+)\/(\w+)$/);
    if (!m) return;
    const [, robotId, kind] = m;
    if (kind === "status") {
      state.statuses[robotId] = body;
      onStatusesChanged();
    } else if (kind === "personality") {
      state.personality[robotId] = body;
    } else if (kind === "display") {
      state.display[robotId] = body;
    } else if (kind === "actions") {
      state.actions[robotId] = body.actions || [];
      if (onRobotPage(robotId)) renderActions(robotId);
    } else if (kind === "mode") {
      state.mode[robotId] = (body.mode || "stationary").toLowerCase();
      if (onRobotPage(robotId)) { renderTabBar(); renderDriverCard(robotId); }
    }
  }
}

function onRobotPage(robotId) {
  return state.page === "robot" && state.selected === robotId;
}

function onStatusesChanged() {
  renderSidebarRobots();
  if (state.page === "dashboard") {
    renderRobotGrid();
  }
  if (state.page === "robot" && state.selected) {
    renderRobotHeader(state.selected);
  }
}

// ---------- WebSocket transport (STOMP, push-only) ----------

let stompClient = null;

function startWebSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  stompClient = new StompJs.Client({
    brokerURL: `${proto}://${location.host}/ws`,
    reconnectDelay: 1000,
    maxReconnectDelay: 30000,
    reconnectTimeMode: StompJs.ReconnectionTimeMode.EXPONENTIAL,
  });

  stompClient.onConnect = () => {
    state.wsConnected = true;
    state.wsFailures = 0;
    subscribeAll();
    renderConnIndicator();
  };

  stompClient.onWebSocketClose = () => {
    const wasConnected = state.wsConnected;
    state.wsConnected = false;
    if (!wasConnected) {
      state.wsFailures += 1;
      if (state.wsFailures >= MAX_WS_FAILURES && !state.wsGaveUp) {
        state.wsGaveUp = true;
        stompClient.deactivate();
        toast("WebSocket unavailable — staying on HTTP polling", true);
      }
    }
    renderConnIndicator();
  };

  stompClient.activate();
}

function subscribeAll() {
  if (!state.wsConnected) return;
  stompClient.subscribe("/topic/fleet/status",
      (msg) => handleMessage("/topic/fleet/status", JSON.parse(msg.body)));
  stompClient.subscribe("/topic/fleet/stats",
      (msg) => handleMessage("/topic/fleet/stats", JSON.parse(msg.body)));
  state.robots.forEach((robot) => {
    ["status", "personality", "display", "actions", "mode"].forEach((kind) => {
      const topic = `/topic/robot/${robot.robotId}/${kind}`;
      stompClient.subscribe(topic, (msg) => handleMessage(topic, JSON.parse(msg.body)));
    });
  });
}

function renderConnIndicator() {
  // Transport widget in the navbar (replaces the old debug page section
  // and the footer indicator).
  const el = $("#nav-transport");
  if (!el) return;
  if (state.wsConnected) {
    el.textContent = "Real-time (WebSocket)";
    el.className = "nav-widget-body ok";
  } else {
    el.textContent = `Polling (HTTP)` +
        (state.wsFailures ? ` - ${state.wsFailures} WS failure(s)` : "") +
        (state.wsGaveUp ? " - gave up on WS" : "");
    el.className = "nav-widget-body warn";
  }
}

async function renderHealthWidget() {
  // Orchestrator health in the navbar. /api/health aggregates adapter
  // reachability: healthy (all) / degraded (some) / down (none). Older
  // builds return only {status:"healthy"} — tolerated.
  const el = $("#nav-health");
  if (!el) return;
  try {
    const health = await api("/api/health");
    const robots = health.robots || {};
    const unreachable = Object.entries(robots)
        .filter(([, r]) => r && r.reachable === false)
        .map(([id, r]) => r.name || id);
    el.textContent = `${health.status} - fleet of ${health.fleetSize}` +
        (unreachable.length ? ` - ${unreachable.length} unreachable` : "");
    el.title = unreachable.length
        ? `Unreachable: ${unreachable.join(", ")}` : "All adapters reachable";
    const cls = health.status === "healthy" ? "ok"
        : health.status === "degraded" ? "degraded" : "err";
    el.className = "nav-widget-body " + cls;
  } catch (e) {
    el.textContent = "unreachable";
    el.title = "";
    el.className = "nav-widget-body err";
  }
}

// ---------- polling transport (fallback + pre-connect) ----------

let pollInFlight = false;

async function pollTick() {
  if (state.wsConnected || pollInFlight || document.hidden) return;
  pollInFlight = true;
  try {
    const [statuses, stats] = await Promise.all([
      api("/api/fleet/status"),
      api("/api/fleet/stats"),
    ]);
    handleMessage("/topic/fleet/status", statuses);
    handleMessage("/topic/fleet/stats", stats);

    if (state.page === "robot" && state.selected) {
      await refreshRobotDetail(state.selected);
    }
  } catch (e) {
    const el = $("#nav-transport");
    if (el) {
      el.textContent = "orchestrator unreachable";
      el.className = "nav-widget-body err";
    }
  } finally {
    pollInFlight = false;
  }
}

/** One-shot REST fetch of a robot's detail — instant paint on page open.
 * Mode rides along here too (not just the WS push) since it drives which
 * tabs are even visible — worth refreshing on every poll tick, not just at
 * WS-connect time. */
async function refreshRobotDetail(robotId) {
  try {
    const [actions, mode] = await Promise.all([
      api(`/api/robots/${robotId}/actions/feed?limit=60`),
      api(`/api/robots/${robotId}/mode`),
    ]);
    handleMessage(`/topic/robot/${robotId}/actions`, actions);
    handleMessage(`/topic/robot/${robotId}/mode`, mode);
  } catch { /* adapter offline; feed keeps last state */ }
}

// ---------- router ----------

function route() {
  const slug = decodeURIComponent(location.pathname.replace(/^\/+/, ""));
  const robot = slug &&
      state.robots.find((r) => robotUrlSlug(r.name).toLowerCase() === slug.toLowerCase());
  if (robot) {
    showRobotPage(robot.robotId);
  } else {
    showPage("dashboard");
  }
  $("#sidebar").classList.remove("open");
}

// The robot page's tabs, in order. `page` embeds that file in an iframe;
// tabs without one (actions, specs) are panels in index.html itself.
// `always: true` tabs show regardless of operating mode; the rest only show
// while the robot is in one of `modes` (PERSONALITY_MODES_BRIEF.md — the
// 2026-09-20 GUI overhaul gates most tabs behind the mode you're in, with
// Personality itself as the always-visible landing view/switcher). Fruitfly
// deliberately gets nothing extra: no manual/interactive tabs while
// something else is driving her.
const TABS = [
  { id: "personality", label: "Personality", page: "personality.html", always: true },
  { id: "actions",   label: "Actions",   always: true },
  { id: "senses",    label: "Dashboard", page: "dashboard.html", always: true },
  { id: "mind",      label: "Thoughts",  page: "mind.html", always: true },
  { id: "map",       label: "Map",       page: "map.html", always: true },
  { id: "leash",     label: "Leash",     page: "leash.html", always: true },
  { id: "metrics",   label: "Metrics",   page: "metrics.html", always: true },
  { id: "specs",     label: "Specs",     always: true },
  { id: "control",   label: "Control",      page: "control.html", modes: ["stationary"] },
  { id: "behavior",  label: "Behavior",     page: "behavior.html", modes: ["stationary"] },
  { id: "ears",      label: "Audio input",  page: "ears.html", modes: ["stationary", "roaming"] },
  { id: "voice",     label: "Audio output", page: "voice.html", modes: ["stationary", "roaming"] },
  { id: "eyes",      label: "Vision",       page: "eyes.html", modes: ["stationary", "roaming"] },
];
const FRAME_TABS = TABS.filter((t) => t.page).map((t) => t.id);

function visibleTabs(mode) {
  return TABS.filter((t) => t.always || (t.modes && t.modes.includes(mode)));
}

// Iframes are created once, up front, for every tab regardless of mode —
// cheap (nothing loads until a tab's src is set), and it means a mode
// switch never has to tear down and reload a frame that stays visible.
function renderFrames() {
  $("#robot-frames").innerHTML = TABS.filter((t) => t.page).map((t) =>
      `<div id="robot-tab-${t.id}" class="robot-tab hidden">` +
      `<iframe id="${t.id}-frame" class="control-frame" title="${escapeHtml(t.label)}"></iframe></div>`).join("");
}

// Only the button strip depends on mode; rebuilding it is what actually
// gates the tabs. Falls back to Personality if the active tab just got
// hidden by a mode switch.
function renderTabBar() {
  const mode = state.mode[state.selected] || "stationary";
  const tabs = visibleTabs(mode);
  if (!tabs.some((t) => t.id === state.activeTab)) state.activeTab = "personality";
  $("#tab-bar").innerHTML = tabs.map((t) =>
      `<button class="tab${t.id === state.activeTab ? " active" : ""}" role="tab"` +
      ` aria-selected="${t.id === state.activeTab}" data-tab="${t.id}">${escapeHtml(t.label)}</button>`).join("");
  showActiveTabPanel();
}

function showActiveTabPanel() {
  const name = state.activeTab;
  document.querySelectorAll(".robot-tab").forEach((panel) =>
      panel.classList.toggle("hidden", panel.id !== `robot-tab-${name}`));
  // Tell every embedded page whether it is the visible tab so hidden
  // frames stop polling (common.js listens for this).
  FRAME_TABS.forEach((frameName) => {
    const frame = $(`#${frameName}-frame`);
    if (frame && frame.contentWindow && frame.getAttribute("src")) {
      frame.contentWindow.postMessage(
          { type: "laika-visible", visible: frameName === name }, "*");
    }
  });
  const tabDef = TABS.find((t) => t.id === name);
  if (tabDef && tabDef.page) {
    const frame = $(`#${name}-frame`);
    if (frame && !frame.getAttribute("src")) {
      frame.src = `${tabDef.page}?embedded=1&robot=${encodeURIComponent(state.selected)}`;
    }
  }
  if (name === "specs") {
    renderSpecsPage($("#specs-content"), state.selected);
    loadPollingPanel(state.selected);
  }
}

function activateTab(name) {
  state.activeTab = name;
  renderTabBar();
}

function clearFrames() {
  // Dropping src stops every poll loop inside the embedded pages.
  FRAME_TABS.forEach((name) => {
    const frame = $(`#${name}-frame`);
    if (frame && frame.getAttribute("src")) frame.removeAttribute("src");
  });
}

function resetRobotPanels() {
  if (state.arbiterCard) { state.arbiterCard.stop(); state.arbiterCard = null; }
  if (state.powerCard) { state.powerCard.stop(); state.powerCard = null; }
  if (state.queueCard) { state.queueCard.stop(); state.queueCard = null; }
  $("#arbiter-card").innerHTML = "";
  $("#power-card").innerHTML = "";
  $("#actions").innerHTML = "";
  $("#actions-age").textContent = "";
  document.querySelectorAll("#driver-options .driver-option").forEach((btn) => btn.classList.remove("active"));
  document.querySelectorAll("#sense-options .sense-card").forEach((btn) => btn.classList.remove("active"));
  ["#poll-ttl", "#poll-batt", "#poll-mult", "#poll-postures"].forEach((sel) => {
    $(sel).value = "";
  });
  $("#polling-state").textContent = "";
}

// An embedded page's widget wrench asks for another tab of the same robot.
// (If that tab is mode-hidden, renderTabBar's fallback quietly lands on
// Personality instead — a wrench never opens a tab the current mode hides.)
window.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type !== "laika-open-tab") return;
  if (TABS.some((t) => t.id === data.tab)) activateTab(data.tab);
});

function showPage(page) {
  state.page = page;
  document.querySelectorAll(".page").forEach((s) => s.classList.add("hidden"));
  $(`#page-${page}`).classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((link) =>
      link.classList.toggle("active", link.dataset.page === page));

  if (page === "dashboard") {
    // Leaving a robot page: unload its frames so nothing keeps polling
    // the adapters from behind the dashboard.
    clearFrames();
    resetRobotPanels();
    state.selected = null;
    renderRobotGrid();
  }
  renderSidebarRobots();
}

function showRobotPage(robotId) {
  const robotChanged = state.selected !== robotId;
  state.page = "robot";
  state.selected = robotId;
  document.querySelectorAll(".page").forEach((s) => s.classList.add("hidden"));
  $("#page-robot").classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((link) =>
      link.classList.toggle("active", link.dataset.robot === robotId));

  if (robotChanged) {
    // Embedded tabs are per-robot: clear cached frames, wipe the shared
    // panels and land back on Personality — the mode gate/switcher — so
    // nothing shows the previous robot's data while the new robot's
    // fetches are in flight.
    clearFrames();
    resetRobotPanels();
    state.activeTab = "personality";
  }
  renderTabBar();

  renderRobotHeader(robotId);
  renderActions(robotId);
  renderDriverCard(robotId);
  renderSensesCard(robotId);
  if (!state.arbiterCard) {
    state.arbiterCard = hlArbiterCard($("#arbiter-card"), `/api/robots/${robotId}`,
        { title: "Current behavior", runs: 6 });
    hlLoadBadgePalette(`/api/robots/${robotId}`);
    state.powerCard = hlPowerCard($("#power-card"), `/api/robots/${robotId}`);
    state.queueCard = hlQueueStackCard($("#queue-card"), `/api/robots/${robotId}`);
  }
  refreshRobotDetail(robotId);
  renderSidebarRobots();
}

// ---------- sidebar ----------

function renderSidebarRobots() {
  const container = $("#nav-robots");
  container.innerHTML = "";
  state.robots.forEach((robot) => {
    const status = state.statuses[robot.robotId];
    const link = document.createElement("a");
    link.href = `#robot/${encodeURIComponent(robot.robotId)}`;
    link.className = "nav-link" +
        (state.page === "robot" && state.selected === robot.robotId ? " active" : "");
    link.dataset.robot = robot.robotId;
    link.innerHTML =
        `<span class="label">${escapeHtml(robot.name)}</span>` +
        `<span class="dot ${status?.connected ? "on" : "off"}"></span>`;
    container.appendChild(link);
  });
}

// ---------- dashboard ----------

const MINI_ROBOT_SVG = `
<svg class="robot-mini" viewBox="0 0 100 90" aria-hidden="true">
  <ellipse cx="50" cy="42" rx="26" ry="18"/>
  <circle cx="32" cy="62" r="6"/><circle cx="68" cy="62" r="6"/>
  <circle cx="32" cy="76" r="6"/><circle cx="68" cy="76" r="6"/>
  <line x1="50" y1="30" x2="70" y2="16"/><circle cx="70" cy="16" r="4"/>
</svg>`;

function renderRobotGrid() {
  const container = $("#robot-grid");
  container.innerHTML = "";
  state.robots.forEach((robot) => {
    if (!state.devMode && isDevFixtureRobot(robot)) return;
    const card = document.createElement("div");
    card.className = "robot-card";
    card.tabIndex = 0;
    card.setAttribute("role", "link");
    card.setAttribute("aria-label", `${robot.name}: open robot page`);
    card.innerHTML = `
      <div class="status-header">
        <span class="robot-name">${escapeHtml(robot.name)}</span>
        <span class="type-badge">${escapeHtml(robot.type || "?")}</span>
      </div>
      ${MINI_ROBOT_SVG}`;
    const open = () => {
      history.pushState(null, "", `/${encodeURIComponent(robotUrlSlug(robot.name))}`);
      route();
    };
    card.onclick = open;
    card.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    };
    container.appendChild(card);
  });
}

// Battery over the last 24 h from the orchestrator's hourly metric rollups
// (the adapter's /metrics snapshot carries the battery gauge, so every
// rollup row has snapshot.battery). Hidden when there is no history yet.
const sparkCache = {};   // robotId -> {at, points}

async function renderBatterySparkline(robotId, host) {
  if (!host) return;
  const cached = sparkCache[robotId];
  const fresh = cached && Date.now() - cached.at < 5 * 60 * 1000;
  if (!fresh) {
    try {
      const rows = await api(`/api/metrics/history?robotId=${encodeURIComponent(robotId)}&limit=24`);
      const points = (Array.isArray(rows) ? rows : [])
          .map((r) => ({ t: Date.parse(r.hourStart), v: r.snapshot?.battery }))
          .filter((p) => Number.isFinite(p.t) && typeof p.v === "number")
          .sort((a, b) => a.t - b.t);
      sparkCache[robotId] = { at: Date.now(), points };
    } catch {
      sparkCache[robotId] = { at: Date.now(), points: [] };
    }
  }
  const points = sparkCache[robotId].points;
  if (!host.isConnected) return;           // grid re-rendered meanwhile
  if (points.length < 2) { host.innerHTML = ""; return; }
  const w = 120, h = 30;
  const t0 = points[0].t, t1 = points[points.length - 1].t || t0 + 1;
  const x = (t) => (w * (t - t0) / Math.max(1, t1 - t0)).toFixed(1);
  const y = (v) => (h - 2 - (h - 4) * Math.max(0, Math.min(100, v)) / 100).toFixed(1);
  const pts = points.map((p) => `${x(p.t)},${y(p.v)}`).join(" ");
  const first = points[0], last = points[points.length - 1];
  const hours = Math.max(1, Math.round((last.t - first.t) / 3600000));
  host.innerHTML =
      `<div class="spark-label"><span>Battery ${hours}h</span>` +
      `<span>${Math.round(first.v)}% → ${Math.round(last.v)}%</span></div>` +
      `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
      `<line class="spark-floor" x1="0" x2="${w}" y1="${y(20)}" y2="${y(20)}"/>` +
      `<polyline points="${pts}"/></svg>`;
}

// ---------- robot detail ----------

function robotInfo(robotId) {
  return state.robots.find((r) => r.robotId === robotId);
}

function renderRobotHeader(robotId) {
  const robot = robotInfo(robotId);
  const status = state.statuses[robotId] || {};
  // Page title is the robot's configured name (dynamic per robot).
  $("#robot-title").textContent = robot ? robot.name : robotId;
  const conn = $("#robot-chip-conn");
  conn.textContent = status.connected ? "connected" : "disconnected";
  conn.className = "chip " + (status.connected ? "ok" : "err");
  $("#robot-chip-mood").textContent = `mood: ${status.mood ?? "?"}`;
  $("#robot-chip-mode").textContent = `mode: ${status.mode ?? "?"}`;
  renderUptimeChip();
}

// ---------- driver card icons ----------
// Same bell-jar rasterize pipeline as personality.html's mode cards (ported,
// not shared — that page runs in its own iframe/window). Fruitfly reuses its
// exact dome+fly animation; Manual gets a new dome+joystick icon since
// "manual" isn't one of personality.html's bell jars.

const DRIVER_PALETTE = ["#04150a", "#0d3a1e", "#1f6b3f", "#3fbf72", "#8dffb8"];

function driverRasterize(canvas, drawHi) {
  const hi = document.createElement("canvas");
  hi.width = 160; hi.height = 160;
  const hctx = hi.getContext("2d");
  hctx.fillStyle = "#000"; hctx.fillRect(0, 0, 160, 160);
  drawHi(hctx);
  const lw = 26, lh = 26;
  const low = document.createElement("canvas");
  low.width = lw; low.height = lh;
  const lctx = low.getContext("2d");
  lctx.imageSmoothingEnabled = true;
  lctx.drawImage(hi, 0, 0, lw, lh);
  const data = lctx.getImageData(0, 0, lw, lh).data;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const cw = canvas.width / lw, ch = canvas.height / lh;
  for (let y = 0; y < lh; y++) {
    for (let x = 0; x < lw; x++) {
      const i = (y * lw + x) * 4;
      const lum = (data[i] * 0.35 + data[i + 1] * 0.5 + data[i + 2] * 0.15) / 255;
      const level = lum < 0.1 ? 0 : lum < 0.28 ? 1 : lum < 0.5 ? 2 : lum < 0.75 ? 3 : 4;
      ctx.fillStyle = DRIVER_PALETTE[level];
      ctx.fillRect(Math.round(x * cw), Math.round(y * ch), Math.ceil(cw), Math.ceil(ch));
    }
  }
}

function driverDot(ctx, x, y, r) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }

function driverDrawDome(hctx) {
  const cx = 80, topY = 95, r = 52, baseY = 138;
  const leftX = cx - r, rightX = cx + r;
  hctx.strokeStyle = "#cfffe0"; hctx.lineWidth = 5; hctx.lineJoin = "round"; hctx.lineCap = "round";
  hctx.beginPath();
  hctx.arc(cx, topY, r, Math.PI, 0, false);
  hctx.lineTo(rightX, baseY); hctx.lineTo(leftX, baseY); hctx.closePath();
  hctx.stroke();
  hctx.fillStyle = "#1f6b3f"; hctx.fillRect(leftX - 8, baseY, r * 2 + 16, 10);
  hctx.strokeStyle = "rgba(255,255,255,0.45)"; hctx.lineWidth = 3;
  hctx.beginPath(); hctx.arc(cx, topY, 45, Math.PI * 1.12, Math.PI * 1.42, false); hctx.stroke();
}

function driverDrawFly(hctx, t) {
  const jx = 80 + Math.sin(t / 130) * 24 + Math.sin(t / 47) * 6;
  const jy = 92 + Math.cos(t / 97) * 20 + Math.sin(t / 61) * 5;
  const px = 80 + Math.sin((t - 130) / 130) * 24, py = 92 + Math.cos((t - 130) / 97) * 20;
  hctx.strokeStyle = "rgba(180,255,200,0.35)"; hctx.lineWidth = 2; hctx.setLineDash([2, 4]);
  hctx.beginPath(); hctx.moveTo(px, py); hctx.lineTo(jx, jy); hctx.stroke();
  hctx.setLineDash([]);
  hctx.fillStyle = "#cfffe0"; hctx.beginPath(); hctx.ellipse(jx, jy, 4, 6, 0, 0, Math.PI * 2); hctx.fill();
  hctx.fillStyle = "rgba(220,255,230,0.55)";
  hctx.beginPath(); hctx.ellipse(jx - 5, jy - 3, 6, 3, -0.5, 0, Math.PI * 2); hctx.fill();
  hctx.beginPath(); hctx.ellipse(jx + 5, jy - 3, 6, 3, 0.5, 0, Math.PI * 2); hctx.fill();
}

// A small joystick, thumb orbiting the base — "something with hands is
// driving", the opposite read of the fly drifting on its own.
function driverDrawJoystick(hctx, t) {
  const cx = 80, baseY = 112, stickTopY = 80;
  hctx.fillStyle = "#1f6b3f"; hctx.beginPath(); hctx.ellipse(cx, baseY, 22, 9, 0, 0, Math.PI * 2); hctx.fill();
  hctx.strokeStyle = "#cfffe0"; hctx.lineWidth = 5; hctx.lineCap = "round";
  hctx.beginPath(); hctx.moveTo(cx, baseY); hctx.lineTo(cx, stickTopY); hctx.stroke();
  const ang = (t / 900) % (Math.PI * 2);
  const tx = cx + Math.cos(ang) * 7, ty = stickTopY + Math.sin(ang) * 4;
  hctx.fillStyle = "#cfffe0"; driverDot(hctx, tx, ty, 9);
}

const DRIVER_ICON_DRAW = {
  fruitfly: (hctx, t) => { driverDrawDome(hctx); driverDrawFly(hctx, t); },
  manual:   (hctx, t) => { driverDrawDome(hctx); driverDrawJoystick(hctx, t); },
};

const driverReduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function mountDriverIcons() {
  document.querySelectorAll("#driver-options .driver-option").forEach((btn) => {
    const canvas = btn.querySelector(".driver-icon");
    const draw = DRIVER_ICON_DRAW[btn.dataset.icon];
    if (!canvas || !draw) return;
    const frame = () => {
      if (state.page !== "robot") return;   // skip work while off the robot page
      driverRasterize(canvas, (hctx) => draw(hctx, performance.now()));
    };
    frame();
    if (!driverReduceMotion) setInterval(frame, 140);
  });
}
mountDriverIcons();

// Driver: who's piloting the robot. "Manual" switches to stationary mode
// (the only mode with a Control tab for direct driving); "Fruitfly" hands
// her over to the connectome sim. Two buttons for now — see PERSONALITY_
// MODES_BRIEF.md if Roaming/Phone need a slot here later.
function renderDriverCard(robotId) {
  if (!onRobotPage(robotId)) return;
  const mode = state.mode[robotId];
  document.querySelectorAll("#driver-options .driver-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
}

$("#driver-options").addEventListener("click", (e) => {
  const btn = e.target.closest(".driver-option");
  if (!btn || !state.selected) return;
  runAction(btn, async () => {
    const result = await api(`/api/robots/${state.selected}/mode/${btn.dataset.mode}`, { method: "POST" });
    handleMessage(`/topic/robot/${state.selected}/mode`, result);
  });
});

// Senses: six independently-toggled peripherals. Camera and Distance sensor
// reuse pre-existing adapter flags (power-saver no longer touches them —
// POWER_SAVER_ENABLED defaults false), so their status/click shape differs
// slightly from the other four, which got a small new `userEnabled` flag
// each. `field`/`invert` say which status key means "on"; `configEndpoint`
// (Camera only) says the click posts a body to /config instead of hitting
// /enable or /disable.
const SENSES = [
  { domain: "/ears", statusPath: "/ears", field: "enabled" },
  { domain: "/mouth", statusPath: "/mouth", field: "userEnabled" },
  { domain: "/eyes", statusPath: "/eyes", field: "enabled", configEndpoint: true },
  { domain: "/senses/range", statusPath: "/senses/range/status", field: "gated", invert: true },
  { domain: "/mood/led", statusPath: "/mood", field: "userEnabled" },
  { domain: "/senses", statusPath: "/senses", field: "enabled" },
];

function senseIsOn(cfg, body) {
  // A missing key is a wiring bug (wrong field name against the real
  // response), not "off" — surfaced once in the console instead of silently
  // rendering as dim, since that silent failure is exactly how the
  // Microphone card briefly read a field ears.py doesn't expose.
  if (!(cfg.field in body)) {
    console.warn(`Senses: "${cfg.field}" missing from ${cfg.statusPath} response`, body);
  }
  const value = !!body[cfg.field];
  return cfg.invert ? !value : value;
}

async function renderSensesCard(robotId) {
  if (!onRobotPage(robotId)) return;
  await Promise.all(SENSES.map(async (cfg) => {
    const btn = document.querySelector(`#sense-options .sense-card[data-domain="${cfg.domain}"]`);
    if (!btn) return;
    try {
      const body = await api(`/api/robots/${robotId}${cfg.statusPath}`);
      if (!onRobotPage(robotId)) return;   // user moved on; stale answer
      btn.classList.toggle("active", senseIsOn(cfg, body));
    } catch { /* adapter offline; leave the card's last known state */ }
  }));
}

$("#sense-options").addEventListener("click", (e) => {
  const btn = e.target.closest(".sense-card");
  if (!btn || !state.selected) return;
  const cfg = SENSES.find((s) => s.domain === btn.dataset.domain);
  if (!cfg) return;
  const turningOn = !btn.classList.contains("active");
  const label = btn.textContent.trim();
  runAction(btn, async () => {
    const body = cfg.configEndpoint
        ? await api(`/api/robots/${state.selected}${cfg.domain}/config`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: turningOn }),
          })
        : await api(`/api/robots/${state.selected}${cfg.domain}/${turningOn ? "enable" : "disable"}`,
            { method: "POST" });
    btn.classList.toggle("active", senseIsOn(cfg, body));
    announceSenseToggle(label, turningOn);
  });
});

// Dev-mode voice line through the real mouth.say() pipeline — not a toast.
// Best-effort and silent on failure: toggling Speaker itself off is expected
// to mute its own "Speaker disabled" line (play_wav()'s normal gate), not an
// error to surface, and an offline adapter shouldn't spam a toast on top of
// the toggle that already succeeded.
function announceSenseToggle(label, turningOn) {
  if (!state.devMode || !state.devAudioToast || !state.selected) return;
  api(`/api/robots/${state.selected}/mouth/say`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `${label} ${turningOn ? "enabled" : "disabled"}` }),
  }).catch(() => {});
}

// Smooth uptime: derived client-side from the adapter's boot epoch
// (status.startedAt) and ticked every second — no more jumps at the
// polling interval.
function renderUptimeChip() {
  const el = $("#robot-chip-uptime");
  if (!el || state.page !== "robot" || !state.selected) return;
  const status = state.statuses[state.selected] || {};
  if (status.startedAt) {
    el.textContent = "up " + fmtUptime(Math.max(0,
        Math.floor(Date.now() / 1000 - status.startedAt)));
  } else if (status.uptimeSeconds != null) {
    el.textContent = "up " + fmtUptime(status.uptimeSeconds);
  } else {
    el.textContent = "";
  }
}

setInterval(renderUptimeChip, 1000);

// ---------- polling panel (adaptive dog-facing pings) ----------

async function loadPollingPanel(robotId) {
  try {
    const data = await api(`/api/robots/${robotId}/polling`);
    if (state.selected !== robotId) return;   // user moved on; stale answer
    $("#poll-ttl").value = data.config.telemetryTtlS;
    $("#poll-batt").value = data.config.batteryPollS;
    $("#poll-mult").value = data.config.idleMultiplier;
    $("#poll-postures").value = data.config.idlePostures.join(", ");
    $("#polling-state").textContent = data.idle
        ? `idle (x${data.config.idleMultiplier}) - telemetry every ${data.effectiveTelemetryTtlS}s`
        : `active - telemetry every ${data.effectiveTelemetryTtlS}s`;
  } catch { $("#polling-state").textContent = "adapter offline"; }
}

$("#poll-save").onclick = () => runAction($("#poll-save"), async () => {
  await api(`/api/robots/${state.selected}/polling`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      telemetryTtlS: parseFloat($("#poll-ttl").value),
      batteryPollS: parseFloat($("#poll-batt").value),
      idleMultiplier: parseFloat($("#poll-mult").value),
      idlePostures: $("#poll-postures").value,
    }),
  });
  toast("Polling policy saved");
  loadPollingPanel(state.selected);
});

// One line per thing she did: arbiter steps, speech and sound clips (the
// mouth writes those itself — speech never passes through the arbiter), and
// the lifecycle messages that used to live in a separate activity list.
function renderActions(robotId) {
  const feed = $("#actions");
  feed.innerHTML = "";
  (state.actions[robotId] || []).slice(0, 40).forEach((entry) => {
    const li = document.createElement("li");
    const at = actionAt(entry);
    const when = Number.isFinite(at) ? new Date(at).toLocaleTimeString() : "";
    const running = entry.status === "executing" ? ` <span class="muted">…</span>` : "";
    const failed = entry.status === "failed" ? ` <span class="chip warn">failed</span>` : "";
    li.innerHTML = `<span class="kind">${escapeHtml(entry.tag || "")}</span>` +
        `${escapeHtml(entry.action || "")}${running}${failed}` +
        `<span class="at">${when}</span>`;
    feed.appendChild(li);
  });
  renderActionsAge();
}

// The feed stamps epoch seconds; the old activity list used ISO strings.
function actionAt(entry) {
  if (!entry) return NaN;
  if (typeof entry.at === "number") return entry.at * 1000;
  return Date.parse(entry.at);
}

// "12 s ago" under the newest entry, ticking every second so a stale feed
// is obvious without reading clocks.
function fmtAgo(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${s % 60} s ago`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min ago`;
}

function renderActionsAge() {
  const el = $("#actions-age");
  if (!el) return;
  const newest = state.selected ? (state.actions[state.selected] || [])[0] : null;
  const t = actionAt(newest);
  el.textContent = Number.isFinite(t) ? `newest ${fmtAgo(Date.now() - t)}` : "";
}

setInterval(() => {
  if (!document.hidden && state.page === "robot") renderActionsAge();
}, 1000);

// ---------- actions ----------
// (Fleet-wide autonomous handlers removed with their buttons: the legacy
// adapter loop bypasses the behavior arbiter. Replacement is the Director
// toggle — agent-priority arbiter submissions — framework Phase 4.)

$("#sidebar-open").onclick = () => $("#sidebar").classList.toggle("open");

// ---------- dev mode (shows the Mocha mock-fixture card on the landing page) ----------

const DEVMODE_KEY = "hl-devmode";
state.devMode = localStorage.getItem(DEVMODE_KEY) === "1";
const devModeButton = $("#devmode-toggle");

// The toggle and the chevron are two fused .sense-card halves of one pill —
// both carry .active together so the glow reads as a single button, not two.
function renderDevModeButton() {
  devModeButton.classList.toggle("active", state.devMode);
  $("#devmode-settings-toggle").classList.toggle("active", state.devMode);
  $("#debug-card").classList.toggle("hidden", !state.devMode);
}
renderDevModeButton();

devModeButton.onclick = () => {
  state.devMode = !state.devMode;
  localStorage.setItem(DEVMODE_KEY, state.devMode ? "1" : "0");
  renderDevModeButton();
  renderRobotGrid();
};

// Debug: same call the main-branch speaker card's sound buttons make
// (POST /mouth/play {sound}) — just a single dedicated button, not the
// full sound-library widget.
$("#debug-bark").onclick = () => {
  if (!state.selected) return;
  runAction($("#debug-bark"), () => api(`/api/robots/${state.selected}/mouth/play`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sound: "positive_bark" }),
  }));
};

function isDevFixtureRobot(robot) {
  return (robot.name || "").toLowerCase().startsWith("mocha");
}

// ---- dev mode settings dropdown: a chevron disclosure, not a second
// top-level checkbox — room for more dev-only toggles later without
// crowding the topnav. "Audio toast" (default on) is the first one. ----

const DEV_AUDIO_TOAST_KEY = "hl-dev-audio-toast";
state.devAudioToast = localStorage.getItem(DEV_AUDIO_TOAST_KEY) !== "0";   // default on

const devSettingsToggle = $("#devmode-settings-toggle");
const devSettingsPanel = $("#devmode-settings");
const devAudioToastBtn = $("#devmode-audio-toast");

devAudioToastBtn.classList.toggle("active", state.devAudioToast);

devSettingsToggle.onclick = (e) => {
  e.stopPropagation();
  devSettingsPanel.classList.toggle("hidden");
  const open = !devSettingsPanel.classList.contains("hidden");
  devSettingsToggle.setAttribute("aria-expanded", String(open));
};
document.addEventListener("click", (e) => {
  if (devSettingsPanel.classList.contains("hidden")) return;
  if (e.target === devSettingsToggle || devSettingsPanel.contains(e.target)) return;
  devSettingsPanel.classList.add("hidden");
  devSettingsToggle.setAttribute("aria-expanded", "false");
});

devAudioToastBtn.onclick = () => {
  state.devAudioToast = !state.devAudioToast;
  localStorage.setItem(DEV_AUDIO_TOAST_KEY, state.devAudioToast ? "1" : "0");
  devAudioToastBtn.classList.toggle("active", state.devAudioToast);
};

// Robot page tabs. Embedded per-robot pages lazy-load on first activation
// (frames are cleared whenever the selected robot changes or the user
// returns to the dashboard). The tab bar's buttons are rebuilt on every mode
// change (renderTabBar), so the click listener is delegated on the
// container rather than attached per-button.
renderFrames();
$("#tab-bar").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) activateTab(tab.dataset.tab);
});

// ---------- boot ----------

async function boot() {
  window.addEventListener("popstate", route);
  renderHealthWidget();
  setInterval(() => { if (!document.hidden) renderHealthWidget(); }, 10000);

  try {
    state.robots = await api("/api/fleet/robots");
  } catch (e) {
    toast(`Cannot load fleet: ${e.message}`, true);
  }
  renderSidebarRobots();
  route();

  startWebSocket();
  await pollTick();               // immediate first paint, WS takes over on connect
  setInterval(pollTick, REFRESH_MS);
}

boot();

// Collapsible sidebar — state shared with the sub-pages' nav.js.
(function () {
  const KEY = "heyLaikaNavCollapsed";
  const apply = (c) => document.body.classList.toggle("nav-collapsed", c);
  apply(localStorage.getItem(KEY) === "1");
  const btn = document.getElementById("sidebar-collapse");
  if (btn) btn.addEventListener("click", () => {
    const collapsed = !document.body.classList.contains("nav-collapsed");
    localStorage.setItem(KEY, collapsed ? "1" : "0");
    apply(collapsed);
  });
})();

// The robot header carries "now" so the timestamps in the feeds below can be
// read against it (the adapter stamps in UTC, the browser renders local).
setInterval(() => {
  const clock = $("#sys-clock");
  if (clock) clock.textContent = new Date().toLocaleTimeString();
}, 1000);
