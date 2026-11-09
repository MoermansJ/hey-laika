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
  fruitfly: {},            // robotId -> fruitfly_drive.py's status() (observability only)
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
    } else if (kind === "fruitfly") {
      state.fruitfly[robotId] = body;
      if (onRobotPage(robotId)) renderFruitflyCard(robotId);
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
    ["status", "personality", "display", "actions", "mode", "fruitfly"].forEach((kind) => {
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
    const [actions, mode, fruitfly] = await Promise.all([
      // dog/app/app.py's /actions/feed caps limit at 50 -- this whole
      // Promise.all was silently failing with "'limit' must be <= 50" on
      // every call (a pre-existing bug: 60 was always over that cap), which
      // meant mode/actions never updated at all whenever the WS fallback
      // path was the one actually running.
      api(`/api/robots/${robotId}/actions/feed?limit=50`),
      api(`/api/robots/${robotId}/mode`),
      api(`/api/robots/${robotId}/fruitfly/status`),
    ]);
    handleMessage(`/topic/robot/${robotId}/actions`, actions);
    handleMessage(`/topic/robot/${robotId}/mode`, mode);
    handleMessage(`/topic/robot/${robotId}/fruitfly`, fruitfly);
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
  $("#driver-options").classList.add("hidden");
  $("#driver-dropdown-toggle").setAttribute("aria-expanded", "false");
  $("#driver-active-slot").dataset.icon = "";
  $("#driver-active-label").textContent = "—";
  document.querySelectorAll("#sense-options .sense-card").forEach((btn) => btn.classList.remove("active"));
  ["#poll-ttl", "#poll-batt", "#poll-mult", "#poll-postures"].forEach((sel) => {
    $(sel).value = "";
  });
  $("#polling-state").textContent = "";
  $("#nav-banner").classList.add("hidden");
  $("#nav-cancel").classList.add("hidden");
  sweepDialGeom = null;
  sweepGhostPoint = null;
  sweepPinPoint = null;
  updateWalkButton();
  $("#camera-feed-img").classList.add("hidden");
  $("#camera-feed-img").removeAttribute("src");
  $("#camera-feed-empty").textContent = "loading…";
  $("#camera-feed-empty").classList.remove("hidden");
  $("#fruitfly-body").innerHTML = `<div class="empty">not in Fruitfly mode</div>`;
  $("#fruitfly-age").textContent = "";
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
  renderNavCard(robotId);
  renderPostureDial(robotId);
  renderCameraCard(robotId);
  renderFruitflyCard(robotId);
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
  // .driver-option, not #driver-options .driver-option: the always-shown
  // active slot lives outside the dropdown list and needs the same
  // animated icon. Looking up the draw function fresh every frame (not
  // once at mount) is what lets renderDriverCard swap the slot's
  // dataset.icon later and have the next tick just pick it up.
  document.querySelectorAll(".driver-option").forEach((btn) => {
    const canvas = btn.querySelector(".driver-icon");
    if (!canvas) return;
    const frame = () => {
      if (state.page !== "robot") return;   // skip work while off the robot page
      const draw = DRIVER_ICON_DRAW[btn.dataset.icon];
      if (!draw) return;
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
//
// The active one is always shown in its own slot next to the dropdown
// chevron; the dropdown list (opened/closed separately) shows every
// option, its own active entry faded since re-picking it is a no-op.
function renderDriverCard(robotId) {
  if (!onRobotPage(robotId)) return;
  const mode = state.mode[robotId];
  const match = document.querySelector(`#driver-options .driver-option[data-mode="${mode}"]`);
  const slot = $("#driver-active-slot");
  slot.dataset.icon = match ? match.dataset.icon : "";
  $("#driver-active-label").textContent = match ? match.querySelector(".driver-label").textContent : "—";
  document.querySelectorAll("#driver-options .driver-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
}

const driverToggle = $("#driver-dropdown-toggle");
const driverDropdown = $("#driver-options");
driverToggle.addEventListener("click", (e) => {
  e.stopPropagation();
  driverDropdown.classList.toggle("hidden");
  driverToggle.setAttribute("aria-expanded", String(!driverDropdown.classList.contains("hidden")));
});
document.addEventListener("click", (e) => {
  if (driverDropdown.classList.contains("hidden")) return;
  if (driverDropdown.contains(e.target) || driverToggle.contains(e.target)) return;
  driverDropdown.classList.add("hidden");
  driverToggle.setAttribute("aria-expanded", "false");
});

driverDropdown.addEventListener("click", (e) => {
  const btn = e.target.closest(".driver-option");
  if (!btn || !state.selected) return;
  driverDropdown.classList.add("hidden");
  driverToggle.setAttribute("aria-expanded", "false");
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

// ---------- camera card (live satellite feed under Driver) ----------
// Polls /eyes status (same fields the Adapters > Camera sense card already
// reads) to decide what to show, then refreshes the <img> from the cached
// /eyes/snap JPEG -- no fresh=1, so this rides the adapter's own grab loop
// instead of forcing an extra satellite round trip every tick/tab.

async function renderCameraCard(robotId) {
  if (!onRobotPage(robotId)) return;
  const img = $("#camera-feed-img");
  const empty = $("#camera-feed-empty");
  const age = $("#camera-age");
  let status;
  try {
    status = await api(`/api/robots/${robotId}/eyes`);
  } catch {
    if (onRobotPage(robotId)) {
      img.classList.add("hidden");
      empty.classList.remove("hidden");
      empty.textContent = "adapter offline";
      age.textContent = "";
    }
    return;
  }
  if (!onRobotPage(robotId)) return;
  if (!status.configured) {
    img.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = "no camera configured";
    age.textContent = "";
    return;
  }
  if (!status.streaming) {
    img.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = "no signal";
    age.textContent = "";
    return;
  }
  empty.classList.add("hidden");
  img.classList.remove("hidden");
  img.src = `/api/robots/${robotId}/eyes/snap?t=${Date.now()}`;
  age.textContent = `${status.fps.toFixed(1)} fps`;
}

// ---------- fruitfly card (what the camera->brain pipeline is doing) ----
// Rides the existing fruitfly_drive.py status broadcast (STOMP topic
// "fruitfly", already polled+published server-side -- see
// BroadcastFruitflyUseCase.java -- this was just never rendered anywhere).
// gfRateHz/gfSpikes/lastGfAt/lastEscapeAt were added to that status()
// payload alongside it so this card doesn't need its own new backend route.

const GF_ESCAPE_HZ = 30;     // keep in sync with gf_server.py's ESCAPE_HZ -- the bar's threshold marker only
const GF_BAR_MAX_HZ = 120;   // visual scale; README's measured looming range is 56-192Hz

function renderFruitflyCard(robotId) {
  if (!onRobotPage(robotId)) return;
  const body = $("#fruitfly-body");
  const age = $("#fruitfly-age");
  const mode = state.mode[robotId];
  const ff = state.fruitfly[robotId];
  if (mode !== "fruitfly" || !ff) {
    body.innerHTML = `<div class="empty">not in Fruitfly mode</div>`;
    age.textContent = "";
    return;
  }
  age.textContent = "live";
  const now = Date.now() / 1000;
  const rate = ff.gfRateHz ?? 0;
  const barPct = Math.min(100, (rate / GF_BAR_MAX_HZ) * 100);
  const overThreshold = rate >= GF_ESCAPE_HZ;
  const escapedRecently = ff.lastEscapeAt != null && (now - ff.lastEscapeAt) < 2;
  const gfAgeMs = ff.lastGfAt != null ? (now - ff.lastGfAt) * 1000 : null;
  const escapeAgeMs = ff.lastEscapeAt != null ? (now - ff.lastEscapeAt) * 1000 : null;

  body.innerHTML = `
    <div class="fruitfly-row">
      <span>Camera input (giant fiber)</span>
      <span class="fruitfly-value">${ff.gfEnabled ? `${rate.toFixed(1)} Hz` : "sidecar not running"}</span>
    </div>
    ${ff.gfEnabled ? `
    <div class="fruitfly-bar" title="escape threshold: ${GF_ESCAPE_HZ} Hz">
      <div class="fruitfly-bar-fill${overThreshold ? " over" : ""}" style="width:${barPct}%"></div>
      <div class="fruitfly-bar-threshold" style="left:${Math.min(100, (GF_ESCAPE_HZ / GF_BAR_MAX_HZ) * 100)}%"></div>
    </div>
    <div class="fruitfly-row">
      <span>Decision</span>
      <span class="fruitfly-value${escapedRecently ? " escape" : ""}">${
          escapedRecently ? "ESCAPE — jumped" : overThreshold ? "crossing threshold…" : "watching"}</span>
    </div>
    <div class="fruitfly-row muted">
      <span>last spike</span><span>${gfAgeMs != null ? fmtAgo(gfAgeMs) : "never"}</span>
    </div>
    <div class="fruitfly-row muted">
      <span>last jump</span><span>${escapeAgeMs != null ? fmtAgo(escapeAgeMs) : "never"}</span>
    </div>` : ""}
    <div class="fruitfly-row">
      <span>Wander (no camera input)</span>
      <span class="fruitfly-value">${escapeHtml(ff.lastState || "—")}</span>
    </div>
    <p class="fruitfly-legend">Two independent inputs drive her here. A sustained giant-fiber
      burst above ${GF_ESCAPE_HZ} Hz from the camera → one jump (<code>kjmp</code>) then recover
      (<code>kbalance</code>), rate-limited to roughly one per few seconds. Everything else
      (FORWARD / LEFT / RIGHT / STOP above) is a separate, open-loop simulation with no camera or
      sensor input at all — just internally generated wandering, unrelated to anything in view.</p>`;
}

// ---------- navigation card (occupancy map + click-to-walk) ----------
// The glance-and-click version of the Map tab: scan the room, see the
// grid she's built from the sonar sweeps, click a point to walk there.
// Error recovery (trust_sensor/trust_map/manual) stays on the full Map
// tab -- this banner just says something needs a human and links there.

// {cx, cy, R, maxRangeCm, pose} from the latest sweep-dial render, for
// converting a click into a world (x,y) navigation target and back.
let sweepDialGeom = null;
let lastNav = null;   // so zoom/pin redraws can happen locally instead of refetching
let sweepZoom = 1;
const SWEEP_ZOOM_MIN = 0.4, SWEEP_ZOOM_MAX = 2.5;
const clampSweepZoom = (z) => Math.max(SWEEP_ZOOM_MIN, Math.min(SWEEP_ZOOM_MAX, z));

// Pin-a-point-and-walk: a single target point snapped to the nearest of the
// dial's own spoke angles (nav.config.sweepAngles -- "an axis", not an
// arbitrary direction). sweepGhostPoint previews where a click would land
// as the cursor moves; sweepPinPoint is the committed target the Walk
// button acts on. Both are {panDeg, distCm} or null.
let sweepGhostPoint = null;
let sweepPinPoint = null;

function navStateClass(navState) {
  if (navState === "arrived") return "arrived";
  if (navState === "blocked" || navState === "routing") return "blocked";
  if (navState === "error") return "error";
  return "";
}

async function renderNavCard(robotId) {
  if (!onRobotPage(robotId)) return;
  let nav;
  try {
    nav = await api(`/api/robots/${robotId}/navigation`);
  } catch {
    return;
  }
  if (!onRobotPage(robotId)) return;   // user moved on; stale answer

  const t = nav.target;
  $("#nav-cancel").classList.toggle("hidden", !t);

  const banner = $("#nav-banner");
  const err = nav.errors?.active;
  if (err) {
    banner.classList.remove("hidden");
    banner.innerHTML = `<b>She needs help:</b> ${escapeHtml(err.kind)} — ${escapeHtml(err.message)} ` +
      `<a href="/map.html?robot=${encodeURIComponent(robotId)}" target="_blank" rel="noopener">resolve on the Map tab</a>`;
  } else {
    banner.classList.add("hidden");
  }

  renderSweepDial(nav);
}

// The "Scan room" sweep's 7 readings as a radar semicircle: 12 o'clock is
// straight ahead (panDeg 0), 9/3 o'clock are the +/-90 degree ends — the
// same robot-relative convention the sweep angles themselves already use,
// so no heading correction is needed. A chevron marks 12 o'clock; each
// reading is a radial line out to its distance, red when the backend
// flagged it as contradicting the map (map_builder.py's integrate_sweep).
function renderSweepDial(nav) {
  lastNav = nav;
  const el = $("#sweep-dial");
  const ageEl = $("#sweep-age");
  const sweep = nav.lastSweep;
  if (!sweep || !sweep.readings?.length) {
    el.innerHTML = `<div class="empty">no scan yet — click "Update"</div>`;
    ageEl.textContent = "";
    return;
  }
  ageEl.textContent = sweep.at ? `${Math.max(0, Math.round(Date.now() / 1000 - sweep.at))}s ago` : "";

  const cfg = nav.map?.config || {};
  const maxRangeCm = (cfg.maxRangeM ?? 2.0) * 100;
  const minRangeCm = cfg.minRangeCm ?? 4.0;

  const W = 320, H = 200, cx = W / 2, cy = H - 24;
  // R (the rim/bezel) is fixed — zoom doesn't resize or move it off-screen,
  // it narrows or widens the distance this fixed-size dial covers instead,
  // like a radar's range ring changing inside a bezel that never moves.
  const R = Math.min(W / 2 - 24, cy - 28);
  const effMaxRangeCm = maxRangeCm / sweepZoom;
  const sweepAngles = nav.config?.sweepAngles?.length ? nav.config.sweepAngles
      : [-90, -60, -30, 0, 30, 60, 90];
  sweepDialGeom = { W, H, cx, cy, R, maxRangeCm: effMaxRangeCm, pose: nav.pose, sweepAngles };
  // panDeg 0 = straight up (12 o'clock); -90/+90 = left/right (9/3 o'clock).
  const point = (panDeg, radius) => {
    const rad = (90 - panDeg) * Math.PI / 180;
    return [cx + radius * Math.cos(rad), cy - radius * Math.sin(rad)];
  };
  const arcPath = (radius) => {
    const [x0, y0] = point(-90, radius), [x1, y1] = point(90, radius);
    return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${radius.toFixed(1)} ${radius.toFixed(1)} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  };

  let html = `<svg viewBox="0 0 ${W} ${H}">`;

  // outer rim = max range
  html += `<path d="${arcPath(R)}" fill="none" stroke="var(--border)" stroke-width="1.5"/>`;

  // minimum-range threshold: readings this close are noise, not real
  // (map_builder.py's minRangeCm) — just the dashed arc, no caption label
  const minR = Math.max(4, (minRangeCm / effMaxRangeCm) * R);
  html += `<path d="${arcPath(minR)}" fill="none" stroke="var(--warning)" stroke-width="1" stroke-dasharray="3 3"/>`;

  // range rings every 20cm, for gauging a pinned point's distance by eye --
  // fixed cm steps (not fixed on-screen spacing), so zooming in/out changes
  // how many rings fit rather than what they mean. Labels only every other
  // ring (and off the horizontal baseline, at 75 deg) -- at 20cm steps on
  // a ~200cm range, labelling every ring crams 9 of them into the same
  // row and they overlap.
  const RING_STEP_CM = 20;
  let ringIndex = 0;
  for (let d = RING_STEP_CM; d < effMaxRangeCm - 1; d += RING_STEP_CM, ringIndex++) {
    const ringR = (d / effMaxRangeCm) * R;
    html += `<path d="${arcPath(ringR)}" fill="none" stroke="var(--border)" stroke-width="1" opacity="0.5"/>`;
    if (ringIndex % 2 === 1) {
      const [rx, ry] = point(75, ringR);
      html += `<text x="${rx.toFixed(1)}" y="${ry.toFixed(1)}" text-anchor="middle" font-size="8" ` +
          `fill="var(--text-light)" opacity="0.7">${d}</text>`;
    }
  }

  // chevron at 12 o'clock: forward
  const [chx, chy] = point(0, R + 11);
  html += `<polygon points="${(chx - 5).toFixed(1)},${(chy + 7).toFixed(1)} ${(chx + 5).toFixed(1)},${(chy + 7).toFixed(1)} ${chx.toFixed(1)},${(chy - 3).toFixed(1)}" fill="#ffcc4d"/>`;

  // scan lines: one per reading, out to its measured distance (clamped to
  // the rim if zoomed in far enough that it would otherwise reach past it)
  sweep.readings.forEach((rdg) => {
    const hasRange = rdg.rangeCm != null;
    const dist = hasRange ? Math.min(rdg.rangeCm, effMaxRangeCm) : effMaxRangeCm;
    const radius = (dist / effMaxRangeCm) * R;
    const [ex, ey] = point(rdg.panDeg, radius);
    const color = rdg.conflict ? "var(--danger)" : (hasRange ? "var(--accent)" : "var(--text-light)");
    const dash = hasRange ? "" : ` stroke-dasharray="2 3"`;
    html += `<line x1="${cx}" y1="${cy}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${color}" stroke-width="2"${dash}/>`;
    html += `<circle cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="3" fill="${color}"/>`;
    const [lx, ly] = point(rdg.panDeg, radius + 13);
    const label = hasRange ? `${Math.round(rdg.rangeCm)}` : "—";
    html += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" font-size="9" fill="${color}">${label}</text>`;
  });

  // where she's walking to, if anywhere — world (x,y) converted into this
  // dial's robot-relative polar space, same convention as a click-to-walk
  // click (worldToLocal below), just run the other direction
  if (nav.target && nav.pose) {
    const dx = nav.target.x - nav.pose.x, dy = nav.target.y - nav.pose.y;
    const distCm = Math.hypot(dx, dy) * 100;
    const bearingDeg = Math.atan2(dy, dx) * 180 / Math.PI;
    const panDeg = bearingDeg - nav.pose.heading;
    const radius = Math.min(distCm, effMaxRangeCm) / effMaxRangeCm * R;
    const [tx, ty] = point(panDeg, radius);
    html += `<circle cx="${tx.toFixed(1)}" cy="${ty.toFixed(1)}" r="6" fill="none" stroke="var(--accent)" stroke-width="1.5"/>`;
    html += `<line x1="${cx}" y1="${cy}" x2="${tx.toFixed(1)}" y2="${ty.toFixed(1)}" stroke="var(--accent)" stroke-width="1" stroke-dasharray="4 3" opacity="0.6"/>`;
  }

  // The committed pin the Walk button acts on, then the ghost preview on
  // top of it — the ghost keeps tracking the cursor even with a point
  // already pinned, since clicking it replaces that pin (drawn last so the
  // live preview is never hidden behind the committed marker).
  if (sweepPinPoint) {
    const radius = Math.min(sweepPinPoint.distCm, effMaxRangeCm) / effMaxRangeCm * R;
    const [px, py] = point(sweepPinPoint.panDeg, radius);
    html += `<line x1="${cx}" y1="${cy}" x2="${px.toFixed(1)}" y2="${py.toFixed(1)}" ` +
        `stroke="var(--success)" stroke-width="2"/>`;
    html += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="6" fill="var(--success)"/>`;
    const distM = (sweepPinPoint.distCm / 100).toFixed(2);
    const [lx, ly] = point(sweepPinPoint.panDeg, radius + 15);
    html += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" font-size="9" ` +
        `fill="var(--success)">${distM} m</text>`;
  }
  if (sweepGhostPoint) {
    const radius = Math.min(sweepGhostPoint.distCm, effMaxRangeCm) / effMaxRangeCm * R;
    const [gx, gy] = point(sweepGhostPoint.panDeg, radius);
    html += `<line x1="${cx}" y1="${cy}" x2="${gx.toFixed(1)}" y2="${gy.toFixed(1)}" ` +
        `stroke="var(--text-light)" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.7"/>`;
    html += `<circle cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" r="5" fill="none" ` +
        `stroke="var(--text-light)" stroke-width="1.5" opacity="0.7"/>`;
    const clampedCm = Math.min(sweepGhostPoint.distCm, effMaxRangeCm);
    html += `<text x="${(gx + 8).toFixed(1)}" y="${(gy - 8).toFixed(1)}" font-size="9" ` +
        `fill="var(--text-light)" opacity="0.9">${Math.round(clampedCm)} cm</text>`;
  }

  // robot's position at the dial's center
  html += `<circle cx="${cx}" cy="${cy}" r="4" fill="var(--text)"/>`;

  html += `</svg>`;
  el.innerHTML = html;
  updateWalkButton();
}

function updateWalkButton() {
  const btn = $("#nav-walk");
  if (!btn) return;
  btn.disabled = !sweepPinPoint;
  btn.title = sweepPinPoint ? "Walk to the pinned point" : "Pin a point on one of the dial's spokes first";
  // The projected travel distance straight along the pinned spoke -- shown
  // right on the commit button, not just the small label on the dial.
  btn.textContent = sweepPinPoint ? `Walk (${(sweepPinPoint.distCm / 100).toFixed(2)} m)` : "Walk";
}

// ---------- posture dial: 3D wireframe of the current joint angles + body
// tilt, orbited by click-drag. Polls GET /posture (joint angles + the gp
// pitch/roll the mood/nav code already reads for yaw) on its own 2s timer.
//
// Geometry is approximate, not a precision CAD overlay: segment lengths and
// shoulder-mount offsets are scaled from sim/bittle-simulation/models/
// bittle.urdf (a real Petoi-published kinematic model already in this repo)
// against the Bittle X's published 190x153x107mm standing footprint
// (petoi.com/pages/robot-dog-bittle-x-technical-specifications). The
// URDF's own units aren't literal meters, so the scale (~146mm per URDF
// unit) was derived by matching its shoulder-span geometry to that real
// footprint, cross-checked against width and height for consistency. Shin
// length doubles the URDF knee-link's own inertial offset (a COM-to-joint
// proxy, doubled on the assumption of roughly uniform mass along the
// segment) since the URDF has no separate foot/toe link to measure to
// directly. Good enough to read posture and body lean; refine if a truer
// source (measured unit or official CAD) turns up.
//
// Hip/knee rotate in the sagittal (fore-aft/vertical) plane per
// robot_schema.py's own joint descriptions ("Hip flexion forward/back",
// "Knee bend extend/contract") rather than replicating the URDF's raw
// per-joint rpy/axis math — mechanically equivalent for a hinge-chain leg,
// much simpler to keep correct. Left/right "forward" sign per leg is a
// single consistent convention, not independently verified against which
// way each physical servo actually swings — the stance width/height and
// relative articulation will still read correctly either way.
// Proportions cross-checked 2026-11 against F:\petoi_bittle_side.jpg (a
// real side-on photo of the robot): slimmer body, near-even thigh/shin
// lengths, legs hanging straight at a neutral (0,0) stance, each segment
// drawn with real width instead of a bare centerline.
const BITTLE_SKELETON = {
  bodyHalfWidth: 60,   // mm, body center to shoulder, left/right
  bodyHalfLength: 78,  // mm, body center to shoulder, front/back
  bodyHeight: 42,      // mm, box extends from bodyZ (bottom) up by this much
  bodyZ: -3,           // mm, shoulder height relative to body center
  headLen: 50,         // mm, neck pivot to nose
  tailLen: 60,         // mm, rump to tail tip (fixed — no tail servo to drive it)
  thighLen: 70,        // mm, hip to knee
  shinLen: 58,         // mm, knee to foot
  tubeHalfWidth: 7,    // mm, half-thickness of the leg/head/tail "tube" wireframe
  // No fixed per-leg knee sign (front/back constants were tried and both
  // failed — see legPoints()'s comment for what actually governs fold
  // direction, derived from real Sit/Stand/Lay poses on Laika, 2026-11).
  legs: [
    { id: "fl", dx: -1, dy: +1, hipIdx: 8, kneeIdx: 12 },
    { id: "fr", dx: +1, dy: +1, hipIdx: 9, kneeIdx: 13 },
    { id: "br", dx: +1, dy: -1, hipIdx: 10, kneeIdx: 14 },
    { id: "bl", dx: -1, dy: -1, hipIdx: 11, kneeIdx: 15 },
  ],
};

// yaw/pitch chosen for a clean, level, mostly-side-on view by default —
// matching how the reference photos (F:\petoi_bittle_side.jpg and
// hoitg.de/Robots-Petoi-Bittle_en.htm) are framed — rather than the
// steeper top-down-leaning angle this had before, which read as the whole
// model tipped face-down into the ground.
const postureCamera = { yaw: 80, pitch: -8, roll: 0 };
// What drawPostureDial() actually reads — the currently-animating (or
// settled) interpolated snapshot, distinct from whatever the latest fetch
// (the animation's target) happens to be.
let displayedPosture = null;
let postureAnimFrame = null;
const POSTURE_TRANSITION_MS = 400;
let postureZoom = 1;
const POSTURE_ZOOM_MIN = 0.4, POSTURE_ZOOM_MAX = 2.5;
const clampZoom = (z) => Math.max(POSTURE_ZOOM_MIN, Math.min(POSTURE_ZOOM_MAX, z));

function deg(n) { return n * Math.PI / 180; }

// Body-frame tilt (IMU pitch/roll) applied before the view's own rotation.
// Pitch negated: confirmed live against Laika mid-sit (gp reported pitch
// -34.9 while physically rear-down/nose-up) that the firmware's sign
// convention is opposite ours — unnegated, a sit pitched the front down
// into a handstand instead of raising it.
function applyBodyTilt([x, y, z], pitchDeg, rollDeg) {
  const p = deg(-pitchDeg), r = deg(rollDeg);
  const x1 = x * Math.cos(r) + z * Math.sin(r);
  const z1 = -x * Math.sin(r) + z * Math.cos(r);
  const y2 = y * Math.cos(p) - z1 * Math.sin(p);
  const z2 = y * Math.sin(p) + z1 * Math.cos(p);
  return [x1, y2, z2];
}

// Camera orbit (drag-controlled view rotation): yaw around world Z, then
// pitch around the resulting X, then roll around the resulting Y — a fixed
// order so each of the three axis buttons spins a stable, predictable axis
// regardless of the other two's current values.
function applyCamera([x, y, z], yawDeg, pitchDeg, rollDeg) {
  const yaw = deg(yawDeg), pitch = deg(pitchDeg), roll = deg(rollDeg);
  const x1 = x * Math.cos(yaw) - y * Math.sin(yaw);
  const y1 = x * Math.sin(yaw) + y * Math.cos(yaw);
  const y2 = y1 * Math.cos(pitch) - z * Math.sin(pitch);
  const z2 = y1 * Math.sin(pitch) + z * Math.cos(pitch);
  const x3 = x1 * Math.cos(roll) + z2 * Math.sin(roll);
  const z3 = -x1 * Math.sin(roll) + z2 * Math.cos(roll);
  return [x3, y2, z3];
}

function legPoints(leg, hipDeg, kneeDeg) {
  const SK = BITTLE_SKELETON;
  const anchor = [leg.dx * SK.bodyHalfWidth, leg.dy * SK.bodyHalfLength, SK.bodyZ];
  const hip = deg(hipDeg);
  const knee = [anchor[0], anchor[1] - SK.thighLen * Math.sin(hip),
                anchor[2] - SK.thighLen * Math.cos(hip)];
  // What actually governs fold direction (checked against real Stand/Sit/
  // Lay angles from Laika, 2026-11 — a fixed per-leg sign and a cos(hip)
  // threshold were both tried and both broke one of the three): whether
  // hip and knee pull the SAME way or OPPOSITE ways.
  //   same sign (stand: 28/28, a sit's front leg: 45/45) -> plain
  //     hip-knee already matches real Laika and must stay untouched.
  //   opposite signs (a sit's hind leg: 105/-45, lay's legs: 75/-55) ->
  //     plain hip-knee pointed the shin up through the body/into the
  //     torso instead of down to the ground; a full 180° flip (negating
  //     both the fore-aft and vertical component) fixes both at once —
  //     lay's legs now descend properly, and a sit's hind foot lands
  //     much closer under the hip instead of floating out behind it.
  const sameSign = hipDeg === 0 || kneeDeg === 0 || Math.sign(hipDeg) === Math.sign(kneeDeg);
  let bend = hip - deg(kneeDeg);
  if (!sameSign) bend += Math.PI;
  // Small constant forward lean on every foot — a standing pose's paws
  // read as very slightly behind the hip without it; purely cosmetic, not
  // tied to any joint reading.
  bend -= deg(8);
  const foot = [knee[0], knee[1] - SK.shinLen * Math.sin(bend),
                knee[2] - SK.shinLen * Math.cos(bend)];
  return [anchor, knee, foot];
}

function headPoint(panDeg) {
  const SK = BITTLE_SKELETON;
  const rad = deg(panDeg);
  const base = [0, SK.bodyHalfLength, SK.bodyZ + SK.bodyHeight * 0.85];
  return [base[0] - SK.headLen * Math.sin(rad), base[1] + SK.headLen * Math.cos(rad), base[2]];
}

// Fixed (no servo drives it): a simple back-and-up curl, matching the
// reference photos' tail shape closely enough to read as a tail.
function tailPoints() {
  const SK = BITTLE_SKELETON;
  const base = [0, -SK.bodyHalfLength, SK.bodyZ + SK.bodyHeight * 0.75];
  const mid = [0, -SK.bodyHalfLength - SK.tailLen * 0.6, base[2] + SK.tailLen * 0.55];
  const tip = [0, -SK.bodyHalfLength - SK.tailLen * 0.35, base[2] + SK.tailLen * 1.05];
  return [base, mid, tip];
}

function bodyBox() {
  const SK = BITTLE_SKELETON;
  const w = SK.bodyHalfWidth, l = SK.bodyHalfLength;
  const zBot = SK.bodyZ, zTop = SK.bodyZ + SK.bodyHeight;
  const corners = (z) => [[-w, l, z], [w, l, z], [w, -l, z], [-w, -l, z]];
  return { bottom: corners(zBot), top: corners(zTop) };
}

// Gives a bare centerline segment real width: two parallel edges offset
// in local X (legs/head/tail mostly sweep in the Y-Z plane, so an X
// offset reads as thickness from most camera angles) plus end caps —
// a wireframe "tube", not a single line, per the volume ask.
function tubeEdges(p0, p1, half = BITTLE_SKELETON.tubeHalfWidth) {
  const a0 = [p0[0] - half, p0[1], p0[2]], a1 = [p0[0] + half, p0[1], p0[2]];
  const b0 = [p1[0] - half, p1[1], p1[2]], b1 = [p1[0] + half, p1[1], p1[2]];
  return [[a0, b0], [a1, b1], [a0, a1], [b0, b1]];
}

// Ground level: the foot height at a neutral (all-zero) stance — a fixed
// plane, not recomputed per pose, so the grid doesn't jump around as the
// legs move (the real floor doesn't move just because she shifts her feet).
const POSTURE_GROUND_Z = legPoints(BITTLE_SKELETON.legs[0], 0, 0)[2][2] - 4;
const POSTURE_GRID_EXTENT = 560, POSTURE_GRID_STEP = 140;   // 4x the footprint, same cell density

async function renderPostureDial(robotId) {
  if (!onRobotPage(robotId)) return;
  let posture;
  try {
    posture = await api(`/api/robots/${robotId}/posture`);
  } catch {
    if (onRobotPage(robotId)) $("#posture-dial").innerHTML = `<div class="empty">adapter offline</div>`;
    return;
  }
  if (!onRobotPage(robotId)) return;
  if (!posture.joints) {
    $("#posture-dial").innerHTML = `<div class="empty">no joint readback</div>`;
    $("#posture-age").textContent = "";
    return;
  }
  $("#posture-age").textContent = "live";
  if (!displayedPosture) {
    displayedPosture = posture;
    drawPostureDial();
  } else {
    animatePostureTo(posture);
  }
}

const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const lerp = (a, b, t) => a + (b - a) * t;

// Interpolates every joint angle (and body pitch/roll) between two full
// posture snapshots — a sit-to-stand transition moves each servo's angle
// smoothly instead of the dial jump-cutting to the new pose every poll.
function interpolatePosture(from, to, t) {
  const joints = to.joints.map((j) => {
    const fromAngle = from.joints.find((f) => f.index === j.index)?.angle ?? j.angle;
    return { index: j.index, angle: lerp(fromAngle, j.angle, t) };
  });
  const f = from.orientation, g = to.orientation;
  const orientation = g ? {
    pitch: lerp(f?.pitch ?? g.pitch, g.pitch, t),
    roll: lerp(f?.roll ?? g.roll, g.roll, t),
    yaw: g.yaw,
  } : null;
  return { joints, orientation };
}

function animatePostureTo(target) {
  if (postureAnimFrame) cancelAnimationFrame(postureAnimFrame);
  const from = displayedPosture;
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / POSTURE_TRANSITION_MS);
    displayedPosture = interpolatePosture(from, target, easeOutCubic(t));
    drawPostureDial();
    postureAnimFrame = t < 1 ? requestAnimationFrame(step) : null;
  };
  postureAnimFrame = requestAnimationFrame(step);
}

function drawPostureDial() {
  if (!displayedPosture) return;
  const el = $("#posture-dial");
  const angleOf = (idx) => displayedPosture.joints.find((j) => j.index === idx)?.angle ?? 0;
  const { pitch = 0, roll = 0 } = displayedPosture.orientation || {};

  // Scale picked so the tail tip down through the ground grid both fit the
  // viewBox at zoom 1 — it was clipping the feet/floor off the bottom
  // before, which read as "paws not touching the ground" even though the
  // underlying geometry was fine.
  const W = 320, H = 200, cx = W / 2, cy = H / 2;
  const scale = 0.48 * postureZoom;
  const { yaw: camYaw, pitch: camPitch, roll: camRoll } = postureCamera;

  const legChains = BITTLE_SKELETON.legs.map((leg) =>
      legPoints(leg, angleOf(leg.hipIdx), angleOf(leg.kneeIdx)));
  // Body height isn't fixed — a real standing/sitting/lying robot's body
  // settles at whatever height its most-extended leg allows, paws on the
  // floor. Shift the whole rigid body+legs assembly (computed at the
  // skeleton's nominal bodyZ above) so the lowest foot lands exactly on
  // the ground, instead of letting bodyZ stay constant and leaving a sit
  // or lie's feet floating or clipping through the grid.
  const bodyZShift = POSTURE_GROUND_Z - Math.min(...legChains.map((c) => c[2][2]));
  // Body (tilt + camera): the robot's own frame, visibly leaning per the
  // IMU, and now riding at the height its legs actually support. Ground
  // (camera only): the real floor, which doesn't tilt or rise just
  // because the robot does — that's the whole point of drawing it.
  const toScreenBody = ([x0, y0, z0]) => {
    const tilted = applyBodyTilt([x0, y0, z0 + bodyZShift], pitch, roll);
    const [x, , z] = applyCamera(tilted, camYaw, camPitch, camRoll);
    return [cx + x * scale, cy - z * scale];
  };
  const toScreenWorld = (p3) => {
    const [x, , z] = applyCamera(p3, camYaw, camPitch, camRoll);
    return [cx + x * scale, cy - z * scale];
  };

  const head = headPoint(angleOf(0));
  const tail = tailPoints();
  const box = bodyBox();

  const poly = (points, proj, extra = "") =>
      `<polyline points="${points.map((p) => proj(p).map((n) => n.toFixed(1)).join(",")).join(" ")}" ${extra}/>`;
  const line = (p0, p1, proj, extra = "") => poly([p0, p1], proj, extra);
  const dot = (p3, proj, r = 2.5, fill = "var(--accent)") => {
    const [x, y] = proj(p3);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${fill}"/>`;
  };
  // Draws a centerline segment as a thin wireframe "tube" (two side edges
  // + end caps) instead of a bare line — the volume for legs/head/tail.
  const tube = (p0, p1, proj, extra, half) =>
      tubeEdges(p0, p1, half).map(([a, b]) => line(a, b, proj, extra)).join("");

  let html = `<svg viewBox="0 0 ${W} ${H}">`;
  // ground grid — world frame, stays level regardless of body tilt
  for (let v = -POSTURE_GRID_EXTENT; v <= POSTURE_GRID_EXTENT; v += POSTURE_GRID_STEP) {
    html += line([v, -POSTURE_GRID_EXTENT, POSTURE_GROUND_Z], [v, POSTURE_GRID_EXTENT, POSTURE_GROUND_Z],
                toScreenWorld, `fill="none" stroke="var(--border)" stroke-width="1"`);
    html += line([-POSTURE_GRID_EXTENT, v, POSTURE_GROUND_Z], [POSTURE_GRID_EXTENT, v, POSTURE_GROUND_Z],
                toScreenWorld, `fill="none" stroke="var(--border)" stroke-width="1"`);
  }
  // body: a real box (bottom loop, top loop, verticals), not a flat outline
  const bodyStroke = `fill="none" stroke="var(--border)" stroke-width="1.5"`;
  html += poly([...box.bottom, box.bottom[0]], toScreenBody, bodyStroke);
  html += poly([...box.top, box.top[0]], toScreenBody, bodyStroke);
  box.bottom.forEach((p, i) => { html += line(p, box.top[i], toScreenBody, bodyStroke); });
  // legs, each segment a tube
  legChains.forEach((chain) => {
    html += tube(chain[0], chain[1], toScreenBody, `fill="none" stroke="var(--accent)" stroke-width="1.5"`);
    html += tube(chain[1], chain[2], toScreenBody, `fill="none" stroke="var(--accent)" stroke-width="1.5"`);
    html += dot(chain[2], toScreenBody, 2.5, "var(--accent)");   // foot
  });
  // head + tail, also tubes
  const neck = [0, BITTLE_SKELETON.bodyHalfLength, BITTLE_SKELETON.bodyZ + BITTLE_SKELETON.bodyHeight * 0.85];
  html += tube(neck, head, toScreenBody, `fill="none" stroke="#ffcc4d" stroke-width="1.5"`);
  html += dot(head, toScreenBody, 3, "#ffcc4d");
  for (let i = 0; i < tail.length - 1; i++) {
    html += tube(tail[i], tail[i + 1], toScreenBody, `fill="none" stroke="var(--border)" stroke-width="1.5"`, 4);
  }
  // body center
  html += dot([0, 0, BITTLE_SKELETON.bodyZ + BITTLE_SKELETON.bodyHeight / 2], toScreenBody, 3, "var(--text)");
  html += `</svg>`;
  el.innerHTML = html;
}

// Drag-to-rotate, shared by the dial itself (free orbit: yaw+pitch
// together) and the three axis buttons (each locked to one fixed axis).
// `onDrag(dx, dy)` gets the pointer delta since the last move and mutates
// postureCamera directly.
function bindPostureDrag(el, onDrag) {
  let dragging = false, lastX = 0, lastY = 0;
  el.addEventListener("pointerdown", (e) => {
    dragging = true;
    lastX = e.clientX; lastY = e.clientY;
    el.classList.add("dragging");
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    onDrag(e.clientX - lastX, e.clientY - lastY);
    lastX = e.clientX; lastY = e.clientY;
    drawPostureDial();
  });
  const stopDrag = () => { dragging = false; el.classList.remove("dragging"); };
  el.addEventListener("pointerup", stopDrag);
  el.addEventListener("pointercancel", stopDrag);
}

const clampPitch = (p) => Math.max(-85, Math.min(85, p));

bindPostureDrag($("#posture-dial"), (dx, dy) => {
  postureCamera.yaw += dx * 0.5;
  postureCamera.pitch = clampPitch(postureCamera.pitch - dy * 0.5);
});
// Each axis button only reads horizontal drag — one consistent gesture
// (drag left/right) across all three, rather than three different ones.
bindPostureDrag($("#posture-axis-x"), (dx) => {
  postureCamera.pitch = clampPitch(postureCamera.pitch + dx * 0.5);
});
bindPostureDrag($("#posture-axis-y"), (dx) => {
  postureCamera.roll += dx * 0.5;
});
bindPostureDrag($("#posture-axis-z"), (dx) => {
  postureCamera.yaw += dx * 0.5;
});

// Zoom: scroll on the dial itself, or click the dedicated +/- buttons.
$("#posture-dial").addEventListener("wheel", (e) => {
  e.preventDefault();
  postureZoom = clampZoom(postureZoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  drawPostureDial();
}, { passive: false });
$("#posture-zoom-in").addEventListener("click", () => {
  postureZoom = clampZoom(postureZoom * 1.2);
  drawPostureDial();
});
$("#posture-zoom-out").addEventListener("click", () => {
  postureZoom = clampZoom(postureZoom / 1.2);
  drawPostureDial();
});

$("#nav-scan").addEventListener("click", () => {
  if (!state.selected) return;
  runAction($("#nav-scan"), async () => {
    await api(`/api/robots/${state.selected}/navigation/sweep`, { method: "POST" });
    await renderNavCard(state.selected);
  });
});

$("#nav-cancel").addEventListener("click", () => {
  if (!state.selected) return;
  runAction($("#nav-cancel"), async () => {
    await api(`/api/robots/${state.selected}/navigation/cancel`, { method: "POST" });
    await renderNavCard(state.selected);
  });
});

// Pin-a-point-and-walk, on the Scan dial instead of a separate occupancy
// map or an instant-click toggle: hovering snaps a ghost preview to the
// nearest of the dial's own spoke angles (nav.config.sweepAngles — "an
// axis", not an arbitrary direction); clicking commits it as the one pin,
// clicking the pin again removes it instead of replacing it. Nothing moves
// her until Walk is pressed — that's the one step that converts the pinned
// (panDeg, distanceCm) into a world (x,y) target, the same bearing =
// heading + pan convention map_builder.py's sweep rays use, just run
// forward instead of cast, and sends it.

function dialPointFromEvent(e) {
  if (!sweepDialGeom) return null;
  const svg = e.currentTarget.querySelector("svg");
  if (!svg) return null;
  const { W, H, cx, cy, R, maxRangeCm, sweepAngles } = sweepDialGeom;
  const rect = svg.getBoundingClientRect();
  const px = (e.clientX - rect.left) / rect.width * W;
  const py = (e.clientY - rect.top) / rect.height * H;
  const dx = px - cx, dy = cy - py;
  const radius = Math.min(Math.hypot(dx, dy), R);
  const rawPanDeg = Math.max(-90, Math.min(90, 90 - Math.atan2(dy, dx) * 180 / Math.PI));
  const panDeg = sweepAngles.reduce((best, a) =>
      Math.abs(a - rawPanDeg) < Math.abs(best - rawPanDeg) ? a : best, sweepAngles[0]);
  const distCm = radius / R * maxRangeCm;
  return { panDeg, distCm };
}

// Screen-space distance between two dial points, for "clicking the pin
// again removes it" — compared the way it looks on screen (a marker you
// click on), not by exact angle/distance equality.
function dialPointScreenDist(a, b) {
  if (!sweepDialGeom || !a || !b) return Infinity;
  const { R, maxRangeCm } = sweepDialGeom;
  const xy = (p) => {
    const radius = Math.min(p.distCm, maxRangeCm) / maxRangeCm * R;
    const rad = (90 - p.panDeg) * Math.PI / 180;
    return [radius * Math.cos(rad), -radius * Math.sin(rad)];
  };
  const [ax, ay] = xy(a), [bx, by] = xy(b);
  return Math.hypot(ax - bx, ay - by);
}

const samePoint = (a, b) => a === b || (a && b && a.panDeg === b.panDeg && a.distCm === b.distCm);

$("#sweep-dial").addEventListener("mousemove", (e) => {
  // The ghost keeps previewing even with a point already pinned -- clicking
  // it overwrites the old pin (same as placing the first one), so you can
  // see where the replacement will land before committing to it.
  if (!sweepDialGeom) return;
  const next = dialPointFromEvent(e);
  if (samePoint(next, sweepGhostPoint)) return;  // same snapped cell -- skip the redraw
  sweepGhostPoint = next;
  if (lastNav) renderSweepDial(lastNav);
});
$("#sweep-dial").addEventListener("mouseleave", () => {
  if (!sweepGhostPoint) return;
  sweepGhostPoint = null;
  if (lastNav) renderSweepDial(lastNav);
});
$("#sweep-dial").addEventListener("click", (e) => {
  const clicked = dialPointFromEvent(e);
  if (!clicked) return;
  sweepPinPoint = (sweepPinPoint && dialPointScreenDist(clicked, sweepPinPoint) < 14)
      ? null : clicked;
  sweepGhostPoint = null;
  if (lastNav) renderSweepDial(lastNav);
});

$("#nav-walk").addEventListener("click", () => {
  if (!sweepPinPoint || !sweepDialGeom?.pose || !state.selected) return;
  const { pose } = sweepDialGeom;
  const { panDeg, distCm } = sweepPinPoint;
  const bearingRad = (pose.heading + panDeg) * Math.PI / 180;
  const x = Math.round((pose.x + (distCm / 100) * Math.cos(bearingRad)) * 100) / 100;
  const y = Math.round((pose.y + (distCm / 100) * Math.sin(bearingRad)) * 100) / 100;
  runAction($("#nav-walk"), async () => {
    await api(`/api/robots/${state.selected}/navigation/target`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y }),
    });
    sweepPinPoint = null;
    await renderNavCard(state.selected);
  });
});

// Zoom: scroll on the dial itself, or the dedicated +/- buttons. Redraws
// from the cached last nav fetch — no need to hit the adapter again just
// to change scale.
$("#sweep-dial").addEventListener("wheel", (e) => {
  e.preventDefault();
  sweepZoom = clampSweepZoom(sweepZoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  if (lastNav) renderSweepDial(lastNav);
}, { passive: false });
$("#sweep-zoom-in").addEventListener("click", () => {
  sweepZoom = clampSweepZoom(sweepZoom * 1.2);
  if (lastNav) renderSweepDial(lastNav);
});
$("#sweep-zoom-out").addEventListener("click", () => {
  sweepZoom = clampSweepZoom(sweepZoom / 1.2);
  if (lastNav) renderSweepDial(lastNav);
});

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

// Dev-mode toggle confirmations: each channel below is a distinct way of
// noticing an adapter flipped, gated by its own settings-panel toggle
// (DEV_TOAST_CHANNELS / #devmode-settings). Adding a new one (vibration,
// a screen flash, ...) means one entry here plus one button in
// #devmode-settings — no other wiring changes. Best-effort and silent on
// failure throughout: toggling Speaker off is expected to mute its own
// "Speaker disabled" line (play_wav()'s normal gate), not an error to
// surface, and an offline adapter shouldn't spam a toast on top of the
// toggle that already succeeded.
const DEV_TOAST_CHANNELS = [
  {
    id: "audio",
    storageKey: "hl-dev-audio-toast",
    buttonId: "devmode-audio-toast",
    defaultOn: true,
    // Voice line through the real mouth.say() pipeline.
    send: (robotId, label, turningOn) => api(`/api/robots/${robotId}/mouth/say`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: `${label} ${turningOn ? "enabled" : "disabled"}` }),
    }),
  },
  {
    id: "led",
    storageKey: "hl-dev-led-toast",
    buttonId: "devmode-led-toast",
    defaultOn: true,
    // User-pickable: colorInputId/colorStorageKey/colorDefault wire up a
    // <input type="color"> next to the toggle (see the setup loop below).
    // Any future channel can opt into the same pattern the same way.
    colorInputId: "devmode-led-toast-color",
    colorStorageKey: "hl-dev-led-toast-color",
    colorDefault: "#4dff8c",
    // Visual flash through the real mood LED, in the picked colour.
    // seconds=3, not 1: the audio channel's mouth.say() call also flashes
    // the "speaking" mood (teal, pulsing) for the full length of the
    // spoken confirmation line, and hold_color only outranks it for as
    // long as THIS hold is active — once it expired at 1s, "speaking" (for
    // anything longer than a couple words) took back over and read as a
    // stray flashing blue/cyan (2026-11). 3s comfortably outlasts a short
    // toggle confirmation ("Distance sensor disabled") at normal TTS rate.
    // brightness capped well under 255 too: a solid (non-duty-cycled)
    // custom colour can drive two or three LED channels hard at once,
    // unlike most named moods — cheap insurance against satellite/README.md's
    // documented power-rail sag risk (WiFi burst + LED at full white).
    send: (robotId, label, turningOn, color) => {
      const { r, g, b } = hexToRgb(color);
      return api(`/api/robots/${robotId}/mood`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ r, g, b, effect: "solid", seconds: 3, brightness: 120 }),
      });
    },
  },
];

function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

state.devToast = {};
state.devToastColor = {};
DEV_TOAST_CHANNELS.forEach((ch) => {
  state.devToast[ch.id] = localStorage.getItem(ch.storageKey) !== null
      ? localStorage.getItem(ch.storageKey) === "1"
      : ch.defaultOn;
  const btn = $(`#${ch.buttonId}`);
  btn.classList.toggle("active", state.devToast[ch.id]);
  btn.onclick = () => {
    state.devToast[ch.id] = !state.devToast[ch.id];
    localStorage.setItem(ch.storageKey, state.devToast[ch.id] ? "1" : "0");
    btn.classList.toggle("active", state.devToast[ch.id]);
  };

  if (ch.colorInputId) {
    state.devToastColor[ch.id] = localStorage.getItem(ch.colorStorageKey) || ch.colorDefault;
    const colorInput = $(`#${ch.colorInputId}`);
    colorInput.value = state.devToastColor[ch.id];
    colorInput.oninput = () => {
      state.devToastColor[ch.id] = colorInput.value;
      localStorage.setItem(ch.colorStorageKey, colorInput.value);
    };
  }
});

function announceSenseToggle(label, turningOn) {
  if (!state.devMode || !state.selected) return;
  const robotId = state.selected;
  DEV_TOAST_CHANNELS.forEach((ch) => {
    if (!state.devToast[ch.id]) return;
    ch.send(robotId, label, turningOn, state.devToastColor[ch.id]).catch(() => {});
  });
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

// Posture buttons: the same raw skill-token POST /command the stationary
// Control page's Balance/Rest buttons make (control.js's runAction) —
// bypasses the arbiter/execute_action layer entirely, same as the bark
// button above, so it works regardless of what's driving the robot.
const DEBUG_POSTURES = [
  { buttonId: "debug-sit", skill: "ksit" },
  { buttonId: "debug-stand", skill: "kbalance" },
  { buttonId: "debug-lay", skill: "krest" },
];
DEBUG_POSTURES.forEach(({ buttonId, skill }) => {
  const btn = $(`#${buttonId}`);
  btn.onclick = () => {
    if (!state.selected) return;
    runAction(btn, () => api(`/api/robots/${state.selected}/command`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: skill }),
    }));
  };
});

function isDevFixtureRobot(robot) {
  return (robot.name || "").toLowerCase().startsWith("mocha");
}

// ---- dev mode settings dropdown: a chevron disclosure, not a second
// top-level checkbox — room for more dev-only toggles later without
// crowding the topnav. Each toggle's own state/button wiring lives with its
// channel in DEV_TOAST_CHANNELS above; this just opens/closes the panel. ----

const devSettingsToggle = $("#devmode-settings-toggle");
const devSettingsPanel = $("#devmode-settings");

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

// Dismisses whatever navigation error is currently blocking (map
// contradiction, sensor anomaly, ...) the same way the Map tab's "she
// needs help" dialog would, but one click: choice "manual" clears the
// target/route and drops the error without touching the map data (no
// cell corrections applied), same as walking over and picking her up.
$("#devmode-clear-error").onclick = () => {
  if (!state.selected) return;
  runAction($("#devmode-clear-error"), async () => {
    try {
      await api(`/api/robots/${state.selected}/navigation/errors/respond`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice: "manual", note: "cleared via dev-mode button" }),
      });
      toast("Error state cleared");
    } catch (e) {
      if (e.message?.includes("no error is waiting")) toast("No active error");
      else throw e;
    }
  });
};

// Fly-brain sidecar launch buttons: the browser can't spawn a native
// process itself, so these call a tiny always-on helper on this same PC
// (fly-brain-loom/sidecar/launcher.py, localhost:8768 -- not through the
// orchestrator/Docker, since the browser's already on the right machine).
// If that helper isn't running, the fetch itself fails -- surfaced as a
// toast telling Jon to start it once, not a silent no-op.
const FLY_BRAIN_LAUNCHER_URL = "http://localhost:8768";

async function launchFlyBrainSidecar(name, label) {
  let resp;
  try {
    resp = await fetch(`${FLY_BRAIN_LAUNCHER_URL}/launch/${name}`, { method: "POST" });
  } catch {
    throw new Error(`Launcher not reachable at ${FLY_BRAIN_LAUNCHER_URL} — ` +
        `run fly-brain-loom/sidecar/launcher.py once`);
  }
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok || body.ok === false) {
    throw new Error(body.error || `launch failed (HTTP ${resp.status})`);
  }
  toast(body.already ? `${label} already running` : `${label} starting — check its console window`);
}

$("#devmode-launch-gf-server").onclick = () => {
  runAction($("#devmode-launch-gf-server"),
      () => launchFlyBrainSidecar("gf_server", "GF sidecar"));
};
$("#devmode-launch-fly-cam").onclick = () => {
  runAction($("#devmode-launch-fly-cam"),
      () => launchFlyBrainSidecar("fly_cam", "Fly-cam viewer"));
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
  // Navigation state (pose/route/target) has no STOMP push yet, and changes
  // fast enough while she's walking that the one-shot paint in
  // showRobotPage() isn't enough -- poll it on its own, independent of the
  // WS-gated pollTick() above.
  setInterval(() => {
    if (state.page === "robot" && state.selected && !document.hidden) renderNavCard(state.selected);
  }, REFRESH_MS);
  // Posture polls faster (2s, matching control.js's own servo-readback
  // cadence) since joint angles and body tilt are the whole point here —
  // a 4s-stale wireframe during an active scan isn't useful.
  setInterval(() => {
    if (state.page === "robot" && state.selected && !document.hidden) renderPostureDial(state.selected);
  }, 2000);
  // Matches the adapter's own default grab cadence (eyes.py's fps=4.0) —
  // no point polling the cached snapshot faster than it actually refreshes.
  setInterval(() => {
    if (state.page === "robot" && state.selected && !document.hidden) renderCameraCard(state.selected);
  }, 250);

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
