/* Behavior Lab — live view of the autonomous personality loop.
 * Bootstraps from /behavior/history, then streams /topic/robot/{id}/behavior
 * over STOMP; falls back to polling /behavior/status when the socket is down. */
"use strict";

const DIMS = [
  { key: "energy",      label: "Energy",      cssVar: "--s-energy" },
  { key: "happiness",   label: "Happiness",   cssVar: "--s-happiness" },
  { key: "boredom",     label: "Boredom",     cssVar: "--s-boredom" },
  { key: "curiosity",   label: "Curiosity",   cssVar: "--s-curiosity" },
  { key: "hunger",      label: "Hunger",      cssVar: "--s-hunger" },
  { key: "contentment", label: "Contentment", cssVar: "--s-contentment" },
];

const ACTIONS = ["walk_slow", "walk_fast", "stand_up", "sit_down", "lie_down",
  "look_left", "look_right", "look_up", "look_around_low", "look_around_slow",
  "stretch", "play_bow", "backflip", "spin",
  "idle_calm", "sleep", "wake_up", "seek_attention"];

const POSTURE_ICON = { STANDING: "🐕", SITTING: "🪑", LYING: "🛏", SLEEPING: "💤" };
const MAX_POINTS = 600;

const $ = (sel) => document.querySelector(sel);

const state = {
  robots: [],
  robotId: null,
  points: [],           // {t, energy..contentment, posture, action, source, reasoning, success}
  visible: new Set(DIMS.map((d) => d.key)),
  running: null,
  wsConnected: false,
  subscription: null,
};

let stompClient = null;

// ---------- theme-aware colors ----------

function css(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

// ---------- data ----------

function toPoint(decision) {
  const s = decision.stateAtDecision;
  return {
    t: Date.parse(decision.decidedAt),
    energy: s.energy, happiness: s.happiness, boredom: s.boredom,
    curiosity: s.curiosity, hunger: s.hunger, contentment: s.contentment,
    posture: s.posture,
    action: decision.selectedAction,
    source: decision.source,
    reasoning: decision.reasoning,
    success: decision.success,
  };
}

function appendPoint(point) {
  const last = state.points[state.points.length - 1];
  if (last && point.t <= last.t) return false;
  state.points.push(point);
  if (state.points.length > MAX_POINTS) state.points.shift();
  return true;
}

async function loadHistory() {
  const res = await fetch(`/api/robots/${state.robotId}/behavior/history?limit=${MAX_POINTS}`);
  const decisions = await res.json();       // newest first
  state.points = decisions.reverse().map(toPoint);
  renderAll();
}

async function refreshStatus() {
  const res = await fetch(`/api/robots/${state.robotId}/behavior/status`);
  const status = await res.json();
  state.running = status.running;
  renderLoopControls();
  if (!state.wsConnected && status.lastDecision) {
    if (appendPoint(toPoint(status.lastDecision))) renderAll();
  }
}

// ---------- websocket ----------

function connectStomp() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  stompClient = new StompJs.Client({
    brokerURL: `${proto}://${location.host}/ws`,
    reconnectDelay: 1000,
    maxReconnectDelay: 30000,
  });
  stompClient.onConnect = () => {
    state.wsConnected = true;
    renderConn();
    subscribeRobot();
  };
  stompClient.onWebSocketClose = () => {
    state.wsConnected = false;
    state.subscription = null;
    renderConn();
  };
  stompClient.activate();
}

function subscribeRobot() {
  if (state.subscription) state.subscription.unsubscribe();
  state.subscription = stompClient.subscribe(
      `/topic/robot/${state.robotId}/behavior`, (message) => {
        const update = JSON.parse(message.body);
        if (appendPoint(toPoint(update.decision))) renderAll();
      });
}

// ---------- rendering ----------

function renderAll() {
  renderTiles();
  drawChart();
  renderFreq();
  renderDecisions();
}

function renderConn() {
  const chip = $("#conn-chip");
  chip.textContent = state.wsConnected ? "live" : "polling";
  chip.className = "chip " + (state.wsConnected ? "on" : "off");
}

function renderLoopControls() {
  const chip = $("#loop-chip");
  const btn = $("#btn-loop");
  if (state.running === null) { chip.textContent = "…"; return; }
  chip.textContent = state.running ? "loop running" : "loop stopped";
  chip.className = "chip " + (state.running ? "on" : "off");
  btn.textContent = state.running ? "Stop" : "Start";
}

function renderTiles() {
  const latest = state.points[state.points.length - 1];
  const tiles = $("#tiles");
  tiles.innerHTML = "";
  for (const dim of DIMS) {
    const value = latest ? Math.round(latest[dim.key] * 100) : null;
    const color = css(dim.cssVar);
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML =
        `<div class="name"><span class="swatch" style="background:${color}"></span>${dim.label}</div>` +
        `<div class="value">${value === null ? "—" : value + "%"}</div>` +
        `<div class="meter"><div style="width:${value ?? 0}%;background:${color}"></div></div>`;
    tiles.appendChild(tile);
  }
  const stateTile = document.createElement("div");
  stateTile.className = "tile state";
  const posture = latest?.posture ?? "—";
  stateTile.innerHTML =
      `<div class="name">State</div>` +
      `<div class="value">${POSTURE_ICON[posture] ?? ""} ${posture.toLowerCase()}</div>` +
      `<div class="name">${latest?.action ?? "resting"}</div>`;
  tiles.appendChild(stateTile);
}

function renderLegend() {
  const legend = $("#legend");
  legend.innerHTML = "";
  for (const dim of DIMS) {
    const btn = document.createElement("button");
    btn.className = state.visible.has(dim.key) ? "" : "off";
    btn.innerHTML = `<span class="swatch" style="background:${css(dim.cssVar)}"></span>${dim.label}`;
    btn.onclick = () => {
      if (state.visible.has(dim.key)) state.visible.delete(dim.key);
      else state.visible.add(dim.key);
      renderLegend();
      drawChart();
    };
    legend.appendChild(btn);
  }
}

// ---------- chart (canvas) ----------

const PAD = { left: 36, right: 12, top: 18, bottom: 22 };

function chartGeometry(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth;
  const cssHeight = canvas.clientHeight;
  if (canvas.width !== Math.round(cssWidth * dpr)) canvas.width = Math.round(cssWidth * dpr);
  if (canvas.height !== Math.round(cssHeight * dpr)) canvas.height = Math.round(cssHeight * dpr);
  return { dpr, w: cssWidth, h: cssHeight };
}

function xScale(points, w) {
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const span = Math.max(t1 - t0, 1);
  return (t) => PAD.left + ((t - t0) / span) * (w - PAD.left - PAD.right);
}

function yScale(h) {
  return (v) => PAD.top + (1 - v) * (h - PAD.top - PAD.bottom);
}

function drawChart() {
  const canvas = $("#chart");
  const { dpr, w, h } = chartGeometry(canvas);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.font = "11px system-ui, sans-serif";

  const points = state.points;
  const y = yScale(h);

  // grid + y labels (recessive)
  ctx.strokeStyle = css("--grid");
  ctx.fillStyle = css("--muted");
  ctx.lineWidth = 1;
  for (const frac of [0, 0.25, 0.5, 0.75, 1]) {
    const gy = y(frac) + 0.5;
    ctx.beginPath();
    ctx.moveTo(PAD.left, gy);
    ctx.lineTo(w - PAD.right, gy);
    ctx.stroke();
    ctx.fillText(`${frac * 100}%`, 4, gy + 3);
  }

  if (points.length < 2) {
    ctx.fillText("waiting for data…", PAD.left + 10, h / 2);
    $("#window-label").textContent = "";
    return;
  }
  const x = xScale(points, w);

  // time labels at edges
  const fmt = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  ctx.fillStyle = css("--muted");
  ctx.fillText(fmt(points[0].t), PAD.left, h - 7);
  const endLabel = fmt(points[points.length - 1].t);
  ctx.fillText(endLabel, w - PAD.right - ctx.measureText(endLabel).width, h - 7);
  const minutes = Math.max(1, Math.round((points[points.length - 1].t - points[0].t) / 60000));
  $("#window-label").textContent = `(last ~${minutes} min, ${points.length} samples)`;

  // series lines, fixed slot order
  for (const dim of DIMS) {
    if (!state.visible.has(dim.key)) continue;
    ctx.strokeStyle = css(dim.cssVar);
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    points.forEach((p, i) => {
      const px = x(p.t);
      const py = y(p[dim.key]);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }

  // non-idle action markers along the top
  ctx.fillStyle = css("--ink-2");
  for (const p of points) {
    if (!p.action || p.action === "idle_calm") continue;
    ctx.beginPath();
    ctx.arc(x(p.t), PAD.top - 8, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // hover crosshair
  if (hoverIndex !== null && points[hoverIndex]) {
    const hx = x(points[hoverIndex].t);
    ctx.strokeStyle = css("--baseline");
    ctx.beginPath();
    ctx.moveTo(hx + 0.5, PAD.top);
    ctx.lineTo(hx + 0.5, h - PAD.bottom);
    ctx.stroke();
    for (const dim of DIMS) {
      if (!state.visible.has(dim.key)) continue;
      ctx.fillStyle = css(dim.cssVar);
      ctx.beginPath();
      ctx.arc(hx, y(points[hoverIndex][dim.key]), 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

// ---------- tooltip ----------

let hoverIndex = null;

function onChartHover(event) {
  const canvas = $("#chart");
  const rect = canvas.getBoundingClientRect();
  const points = state.points;
  if (points.length < 2) return;
  const x = xScale(points, canvas.clientWidth);
  const mx = event.clientX - rect.left;
  let best = 0;
  let bestDist = Infinity;
  points.forEach((p, i) => {
    const dist = Math.abs(x(p.t) - mx);
    if (dist < bestDist) { bestDist = dist; best = i; }
  });
  hoverIndex = best;
  const p = points[best];

  const tooltip = $("#tooltip");
  const rows = DIMS.filter((d) => state.visible.has(d.key)).map((d) =>
      `<div class="t-row"><span class="k"><span class="swatch" style="background:${css(d.cssVar)}"></span>${d.label}</span>` +
      `<span>${Math.round(p[d.key] * 100)}%</span></div>`).join("");
  const failed = p.success === false ? " <span style='color:var(--critical)'>(failed)</span>" : "";
  tooltip.innerHTML =
      `<div class="t-time">${new Date(p.t).toLocaleTimeString()}</div>` + rows +
      `<div class="t-action">${POSTURE_ICON[p.posture] ?? ""} ${p.action ?? "resting"}${failed}<br>` +
      `<span style="color:var(--muted)">${p.reasoning ?? ""}</span></div>`;
  tooltip.style.display = "block";
  const tipX = mx + 14 + tooltip.offsetWidth > canvas.clientWidth
      ? mx - tooltip.offsetWidth - 10 : mx + 14;
  tooltip.style.left = `${Math.max(0, tipX)}px`;
  tooltip.style.top = "24px";
  drawChart();
}

function onChartLeave() {
  hoverIndex = null;
  $("#tooltip").style.display = "none";
  drawChart();
}

// ---------- side panels ----------

function renderFreq() {
  const counts = new Map();
  for (const p of state.points) {
    if (!p.action) continue;
    counts.set(p.action, (counts.get(p.action) ?? 0) + 1);
  }
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const max = sorted.length ? sorted[0][1] : 1;
  $("#freq").innerHTML = sorted.map(([action, count]) =>
      `<div class="freq-row"><span class="fname">${action}</span>` +
      `<span class="fbar-track"><span class="fbar" style="display:block;width:${(count / max) * 100}%"></span></span>` +
      `<span class="fcount">${count}</span></div>`).join("") ||
      `<span class="hint">no actions yet</span>`;
}

function renderDecisions() {
  const rows = [...state.points].reverse().slice(0, 100).map((p) => {
    const failed = p.success === false ? ` <span class="fail">✗</span>` : "";
    return `<tr><td class="time">${new Date(p.t).toLocaleTimeString()}</td>` +
        `<td>${p.action ?? "<span class='hint'>rest</span>"}${failed}</td>` +
        `<td><span class="src">${p.source ?? ""}</span></td>` +
        `<td>${(p.posture ?? "").toLowerCase()}</td>` +
        `<td>${p.reasoning ?? ""}</td></tr>`;
  });
  $("#decisions").innerHTML = rows.join("");
}

// ---------- controls ----------

async function post(path) {
  const res = await fetch(`/api/robots/${state.robotId}/behavior/${path}`, { method: "POST" });
  if (!res.ok) console.warn("POST failed", path, res.status);
  return res.ok ? res.json() : null;
}

function bindControls() {
  $("#btn-loop").onclick = async () => {
    const status = await post(state.running ? "stop" : "start");
    if (status) { state.running = status.running; renderLoopControls(); }
  };
  document.querySelectorAll("[data-event]").forEach((btn) => {
    btn.onclick = () => post(`event/${btn.dataset.event}`);
  });
  const actionSelect = $("#action-select");
  actionSelect.innerHTML = ACTIONS.map((a) => `<option>${a}</option>`).join("");
  $("#btn-action").onclick = () => post(`action/${actionSelect.value}`);
  $("#robot-select").onchange = async (event) => {
    state.robotId = event.target.value;
    state.points = [];
    await loadHistory();
    await refreshStatus();
    if (state.wsConnected) subscribeRobot();
  };

  const canvas = $("#chart");
  canvas.addEventListener("pointermove", onChartHover);
  canvas.addEventListener("pointerleave", onChartLeave);
}

// ---------- boot ----------

async function boot() {
  const robots = await (await fetch("/api/fleet/robots")).json();
  state.robots = robots;
  const select = $("#robot-select");
  select.innerHTML = robots.map((r) =>
      `<option value="${r.robotId}">${r.name}</option>`).join("");
  state.robotId = robots[0]?.robotId;
  if (!state.robotId) return;

  renderLegend();
  bindControls();
  await loadHistory();
  await refreshStatus();
  connectStomp();

  setInterval(refreshStatus, 3000);
  new ResizeObserver(() => drawChart()).observe($("#chart"));
  window.matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => { renderLegend(); renderAll(); });
}

boot();

// ---------- Lifecycle behaviors (host-managed greeting + idle ladder) ----------

const CMD_LABELS = {
  kup: "Stand up", kstr: "Stretch", kbalance: "Balance",
  ksit: "Sit down", krest: "Lie down",
};

function lifecycleLabel(command) {
  if (command.startsWith("b ")) return "Ready jingle 🎵";
  return CMD_LABELS[command] || command;
}

async function refreshLifecycle() {
  try {
    const g = await (await fetch(`/api/robots/${state.robotId}/greeting`)).json();
    const chip = document.getElementById("greet-chip");
    chip.textContent = g.enabled ? "enabled" : "disabled";
    chip.className = "chip " + (g.enabled ? "on" : "warn");
    document.getElementById("greet-trigger").textContent =
        `Trigger: ${g.trigger ?? "robot comes online"}`;
    document.getElementById("greet-seq").innerHTML = (g.sequence ?? [])
        .map((s) => `<li>${lifecycleLabel(s.command)}` +
                    `<code>${s.command}</code>` +
                    `<span class="dur">${s.settleS}s</span></li>`).join("");
    document.getElementById("greet-runs").textContent =
        g.runs ? `ran ${g.runs}× (${g.lastResult})` : "not run yet";
    document.getElementById("greet-toggle").textContent =
        g.enabled ? "Disable" : "Enable";
    document.getElementById("greet-toggle").dataset.next =
        g.enabled ? "disable" : "enable";

    const idle = await (await fetch(`/api/robots/${state.robotId}/idle`)).json();
    const ichip = document.getElementById("idle-chip");
    ichip.textContent = idle.enabled ? "enabled" : "disabled";
    ichip.className = "chip " + (idle.enabled ? "on" : "warn");
    document.getElementById("idle-seq").innerHTML =
        `<li>After ${idle.sitAfterS}s stationary → Sit down<code>ksit</code></li>` +
        `<li>After ${idle.restAfterS}s stationary → Lie down<code>krest</code></li>` +
        `<li>Any command → back to active</li>`;
    document.getElementById("idle-now").textContent = `state: ${idle.state}`;
    document.getElementById("idle-toggle").textContent =
        idle.enabled ? "Disable" : "Enable";
    document.getElementById("idle-toggle").dataset.next =
        idle.enabled ? "disable" : "enable";
  } catch { /* adapter offline; chips keep last state */ }
}

(function initLifecycle() {
  document.getElementById("greet-run").addEventListener("click", async () => {
    await fetch(`/api/robots/${state.robotId}/greeting/run`, { method: "POST" });
    setTimeout(refreshLifecycle, 1500);
  });
  document.getElementById("greet-toggle").addEventListener("click", async (e) => {
    await fetch(`/api/robots/${state.robotId}/greeting/${e.target.dataset.next}`,
                { method: "POST" });
    refreshLifecycle();
  });
  document.getElementById("idle-toggle").addEventListener("click", async (e) => {
    await fetch(`/api/robots/${state.robotId}/idle/${e.target.dataset.next}`,
                { method: "POST" });
    refreshLifecycle();
  });
  const tryStart = () => {
    if (state.robotId) {
      refreshLifecycle();
      setInterval(refreshLifecycle, 15000);
    } else {
      setTimeout(tryStart, 500);
    }
  };
  tryStart();
})();
