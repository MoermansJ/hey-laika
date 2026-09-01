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
  activity: {},            // robotId -> ActivityEntry[]
  animations: {},          // robotId -> Animation[]
  wsConnected: false,
  wsGaveUp: false,
  wsFailures: 0,
  debug: {},               // topic -> {at, body}
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

function moodEmoji(mood) {
  return { happy: "😊", excited: "🤩", curious: "🧐", bored: "🥱", tired: "😴",
           sad: "😢", playful: "😜", content: "😌" }[mood] || "🐕";
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
  state.debug[topic] = { at: new Date().toLocaleTimeString(), body };

  if (topic === "/topic/fleet/status") {
    state.statuses = body;
    onStatusesChanged();
  } else if (topic === "/topic/fleet/stats") {
    state.stats = body;
    if (state.page === "dashboard") renderStatCards();
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
    } else if (kind === "activity") {
      state.activity[robotId] = body.activity || [];
      if (onRobotPage(robotId)) renderActivity(robotId);
    }
  }

  if (state.page === "debug") renderDebug();
}

function onRobotPage(robotId) {
  return state.page === "robot" && state.selected === robotId;
}

function onStatusesChanged() {
  renderSidebarRobots();
  if (state.page === "dashboard") {
    renderStatCards();
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
    ["status", "personality", "display", "activity"].forEach((kind) => {
      const topic = `/topic/robot/${robot.robotId}/${kind}`;
      stompClient.subscribe(topic, (msg) => handleMessage(topic, JSON.parse(msg.body)));
    });
  });
}

function renderConnIndicator() {
  const el = $("#conn-indicator");
  if (state.wsConnected) {
    el.textContent = "🟢 Real-time (WebSocket)";
    el.className = "conn-indicator ws";
  } else {
    el.textContent = "🟡 Polling (HTTP)";
    el.className = "conn-indicator poll";
  }
}

// ---------- polling transport (fallback + pre-connect) ----------

async function pollTick() {
  if (state.wsConnected) return;
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
    $("#conn-indicator").textContent = `🔴 orchestrator unreachable`;
  }
}

/** One-shot REST fetch of a robot's detail — instant paint on page open. */
async function refreshRobotDetail(robotId) {
  try {
    const activity = await api(`/api/robots/${robotId}/activity`);
    handleMessage(`/topic/robot/${robotId}/activity`, activity);
  } catch { /* adapter offline; feed keeps last state */ }
}

// ---------- router ----------

function route() {
  const hash = location.hash || "#dashboard";
  const robotMatch = hash.match(/^#robot\/(.+)$/);
  if (robotMatch) {
    showRobotPage(decodeURIComponent(robotMatch[1]));
  } else {
    const page = hash.slice(1);
    showPage(["dashboard", "specs", "settings", "debug"].includes(page) ? page : "dashboard");
  }
  $("#sidebar").classList.remove("open");
}

function showPage(page) {
  state.page = page;
  document.querySelectorAll(".page").forEach((s) => s.classList.add("hidden"));
  $(`#page-${page}`).classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((link) =>
      link.classList.toggle("active", link.dataset.page === page));

  if (page === "dashboard") { renderStatCards(); renderRobotGrid(); }
  if (page === "settings") renderSettings();
  if (page === "debug") renderDebug();
  renderSidebarRobots();
}

function showRobotPage(robotId) {
  state.page = "robot";
  state.selected = robotId;
  document.querySelectorAll(".page").forEach((s) => s.classList.add("hidden"));
  $("#page-robot").classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((link) =>
      link.classList.toggle("active", link.dataset.robot === robotId));

  renderRobotHeader(robotId);
  renderActivity(robotId);
  renderArbiter(robotId);
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
        `<span class="icon">🤖</span><span class="label">${escapeHtml(robot.name)}</span>` +
        `<span class="dot ${status?.connected ? "on" : "off"}"></span>`;
    container.appendChild(link);
  });
}

// ---------- dashboard ----------

function renderStatCards() {
  const container = $("#stat-cards");
  const stats = state.stats;
  const batteries = Object.values(state.statuses)
      .map((s) => s.battery).filter((b) => b != null);
  const avgBattery = batteries.length
      ? Math.round(batteries.reduce((a, b) => a + b, 0) / batteries.length) + "%" : "—";

  const cards = [
    ["Robots", stats ? stats.totalRobots : state.robots.length],
    ["Connected", stats ? stats.connectedRobots : "—"],
    ["Avg battery", avgBattery],
  ];
  container.innerHTML = cards.map(([label, value]) =>
      `<div class="stat-card"><div class="value">${value}</div><div class="label">${label}</div></div>`
  ).join("");
}

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
    const status = state.statuses[robot.robotId] || {};
    const card = document.createElement("div");
    card.className = "robot-card";
    card.innerHTML = `
      <div class="status-header">
        <span class="dot ${status.connected ? "on" : "off"}"></span>
        <span class="robot-name">${escapeHtml(robot.name)}</span>
        <span class="type-badge">${escapeHtml(robot.type || "?")}</span>
      </div>
      ${MINI_ROBOT_SVG}
      <div class="quick-stats">
        <div class="stat">
          <div class="label">Battery <span>${fmtBattery(status.battery)}</span></div>
          <div class="bar-track"><div class="bar-fill battery ${batteryClass(status.battery)}"
               style="width:${status.battery ?? 0}%"></div></div>
        </div>
        <div class="stat">
          <div class="label">Mood</div>
          <div class="mood">${status.mood ? escapeHtml(status.mood) + " " + moodEmoji(status.mood) : "—"}</div>
        </div>
      </div>
      <div class="card-actions">
        <button class="btn-details">Details</button>
        <button class="btn-mind">💭 Mind</button>
      </div>`;
    card.querySelector(".btn-details").onclick = () =>
        location.hash = `#robot/${encodeURIComponent(robot.robotId)}`;
    card.querySelector(".btn-mind").onclick = (event) => {
      event.stopPropagation();
      location.href = `mind.html?robot=${encodeURIComponent(robot.robotId)}`;
    };
    card.onclick = (event) => {
      if (event.target.tagName !== "BUTTON") {
        location.hash = `#robot/${encodeURIComponent(robot.robotId)}`;
      }
    };
    container.appendChild(card);
  });
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
}

function renderActivity(robotId) {
  const feed = $("#activity");
  feed.innerHTML = "";
  (state.activity[robotId] || []).slice(0, 30).forEach((entry) => {
    const li = document.createElement("li");
    const at = entry.at ? new Date(entry.at).toLocaleTimeString() : "";
    li.innerHTML = `<span class="kind">${escapeHtml(entry.kind)}</span>` +
        `${escapeHtml(entry.message)}<span class="at">${at}</span>`;
    feed.appendChild(li);
  });
}

// ---------- settings & debug ----------

async function renderSettings() {
  const table = $("#settings-robots");
  const rows = state.robots.map((r) => `
    <tr><td>${escapeHtml(r.robotId)}</td><td>${escapeHtml(r.name)}</td>
        <td>${escapeHtml(r.type)}</td><td><code>${escapeHtml(r.serviceUrl)}</code></td>
        <td>${r.active ? "✔" : "—"}</td></tr>`).join("");
  table.innerHTML =
      "<tr><th>ID</th><th>Name</th><th>Type</th><th>Adapter URL</th><th>Active</th></tr>" + rows;
  try {
    const health = await api("/api/health");
    $("#settings-health").textContent = JSON.stringify(health, null, 2);
  } catch (e) {
    $("#settings-health").textContent = `unreachable: ${e.message}`;
  }
}

function renderDebug() {
  $("#debug-transport").textContent =
      `websocket connected: ${state.wsConnected} · failures: ${state.wsFailures}` +
      `${state.wsGaveUp ? " · gave up (polling permanently)" : ""}`;
  const container = $("#debug-topics");
  container.innerHTML = "";
  Object.entries(state.debug).sort().forEach(([topic, entry]) => {
    const details = document.createElement("details");
    details.innerHTML = `<summary><code>${escapeHtml(topic)}</code>` +
        `<span class="at">${entry.at}</span></summary>` +
        `<pre class="code-block">${escapeHtml(JSON.stringify(entry.body, null, 2).slice(0, 4000))}</pre>`;
    container.appendChild(details);
  });
}

// ---------- actions ----------
// (Fleet-wide autonomous handlers removed with their buttons: the legacy
// adapter loop bypasses the behavior arbiter. Replacement is the Director
// toggle — agent-priority arbiter submissions — framework Phase 4.)

$("#sidebar-open").onclick = () => $("#sidebar").classList.toggle("open");

// ---------- behavior arbiter status (robot page) ----------

async function renderArbiter(robotId) {
  try {
    const status = await api(`/api/robots/${robotId}/arbiter/status`);
    const current = status.current;
    $("#arbiter-current").innerHTML = current
        ? `<strong>${escapeHtml(current.behavior)}</strong>` +
          ` · step ${current.step}/${current.stepTotal}` +
          ` · <span class="muted">${escapeHtml(current.source)}</span>` +
          ` · P${current.priority}` +
          (status.queued.length ? ` · ${status.queued.length} queued` : "")
        : `idle${status.queued.length ? ` · ${status.queued.length} queued` : ""}`;
    const rows = (status.recentRuns || []).slice(0, 6).map((run) => {
      const at = run.startedAt
          ? new Date(run.startedAt).toLocaleTimeString() : "";
      return `<tr><td>${escapeHtml(run.behavior)}</td>` +
          `<td>${escapeHtml(run.status)}</td>` +
          `<td class="muted">${escapeHtml(run.source)}</td>` +
          `<td class="muted">${at}</td></tr>`;
    }).join("");
    $("#arbiter-log").innerHTML = rows
        ? "<tr><th>Behavior</th><th>Status</th><th>Source</th><th>Started</th></tr>" + rows
        : "";
  } catch { /* adapter offline */ }
}

$("#arbiter-stop").onclick = () =>
    api(`/api/robots/${state.selected}/arbiter/stop`, { method: "POST" })
      .then(() => renderArbiter(state.selected))
      .catch((e) => toast(e.message, true));

setInterval(() => {
  if (state.page === "robot" && state.selected) renderArbiter(state.selected);
}, 5000);

// Robot page tabs: Activity | Control (Control Panel embedded, lazy-loaded).
document.querySelectorAll(".tab-bar .tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab-bar .tab").forEach((t) =>
        t.classList.toggle("active", t === tab));
    document.querySelectorAll(".robot-tab").forEach((panel) =>
        panel.classList.toggle("hidden",
            panel.id !== `robot-tab-${tab.dataset.tab}`));
    // Embedded pages lazy-load on first tab activation.
    const frames = { control: "control.html", voice: "voice.html" };
    const src = frames[tab.dataset.tab];
    if (src) {
      const frame = $(`#${tab.dataset.tab}-frame`);
      if (frame && !frame.src) frame.src = `${src}?embedded=1`;
    }
  });
});

// ---------- boot ----------

async function boot() {
  renderSpecsPage($("#specs-content"));
  window.addEventListener("hashchange", route);

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
