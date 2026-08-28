/* Bittle Fleet dashboard — talks only to the orchestrator's own API. */
"use strict";

const REFRESH_MS = 4000;
let selectedRobot = null;
let autonomousRunning = false;
let refreshTimer = null;

const $ = (sel) => document.querySelector(sel);

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

// ---------- fleet overview ----------

async function loadFleet() {
  const [robots, stats] = await Promise.all([
    api("/api/fleet/robots"),
    api("/api/fleet/stats"),
  ]);

  $("#fleet-stats").textContent =
    `${stats.totalRobots} robot(s) · ${stats.connectedRobots} connected · ` +
    `${stats.autonomousRobots} autonomous`;

  const container = $("#robots");
  container.innerHTML = "";
  const statuses = await api("/api/fleet/status");

  robots.forEach((robot) => {
    const status = statuses[robot.robotId] || {};
    const card = document.createElement("div");
    card.className = "robot-card" + (robot.robotId === selectedRobot ? " selected" : "");
    card.innerHTML =
      `<div class="name"><span class="dot ${status.connected ? "on" : "off"}"></span>` +
      `${robot.name}</div>` +
      `<div class="sub">${robot.robotId} · ${robot.type}` +
      `${status.mood ? " · " + status.mood : ""}</div>`;
    card.onclick = () => selectRobot(robot);
    container.appendChild(card);
  });

  if (!selectedRobot && robots.length > 0) {
    selectRobot(robots[0]);
  }
}

// ---------- robot detail ----------

function selectRobot(robot) {
  selectedRobot = robot.robotId;
  $("#robot-detail").classList.remove("hidden");
  $("#detail-name").textContent = robot.name;
  document.querySelectorAll(".robot-card").forEach((c) => c.classList.remove("selected"));
  loadAnimations();
  refreshDetail();
}

async function refreshDetail() {
  if (!selectedRobot) return;
  try {
    const [status, personality, display, activity] = await Promise.all([
      api(`/api/robots/${selectedRobot}/status`),
      api(`/api/robots/${selectedRobot}/personality`),
      api(`/api/robots/${selectedRobot}/display`),
      api(`/api/robots/${selectedRobot}/activity`),
    ]);

    const statusChip = $("#detail-status");
    statusChip.textContent = status.connected ? "connected" : "disconnected";
    statusChip.className = "chip " + (status.connected ? "ok" : "err");
    $("#detail-mood").textContent = `mood: ${personality.mood}`;
    $("#detail-mode").textContent = `mode: ${status.mode ?? "?"}`;

    autonomousRunning = status.autonomous === true;
    const toggle = $("#autonomous-toggle");
    toggle.textContent = autonomousRunning ? "Stop autonomous" : "Start autonomous";
    toggle.classList.toggle("active", autonomousRunning);

    $("#speech").textContent = display.value || "…";

    renderBars(personality);
    renderActivity(activity.activity || []);
  } catch (e) {
    $("#detail-status").textContent = "unreachable";
    $("#detail-status").className = "chip err";
  }
}

function renderBars(p) {
  const container = $("#personality-bars");
  container.innerHTML = "";
  ["energy", "happiness", "boredom", "curiosity"].forEach((key) => {
    const value = p[key];
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML =
      `<div class="bar-label"><span>${key}</span><span>${value}</span></div>` +
      `<div class="bar-track"><div class="bar-fill ${key}" style="width:${value}%"></div></div>`;
    container.appendChild(row);
  });
}

function renderActivity(entries) {
  const feed = $("#activity");
  feed.innerHTML = "";
  entries.slice(0, 30).forEach((entry) => {
    const li = document.createElement("li");
    const at = entry.at ? new Date(entry.at).toLocaleTimeString() : "";
    li.innerHTML =
      `<span class="kind">${entry.kind}</span>${escapeHtml(entry.message)}` +
      `<span class="at">${at}</span>`;
    feed.appendChild(li);
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function loadAnimations() {
  const container = $("#animations");
  container.innerHTML = "<span class='muted'>loading…</span>";
  try {
    const data = await api(`/api/robots/${selectedRobot}/choreography/list`);
    container.innerHTML = "";
    data.animations.forEach((anim) => {
      const btn = document.createElement("button");
      btn.innerHTML = `<span>${anim.name}</span><span class="desc">${anim.description}</span>`;
      btn.onclick = () => runAction(btn, () =>
        api(`/api/robots/${selectedRobot}/choreography/execute/${anim.name}`, { method: "POST" })
          .then(() => toast(`▶ ${anim.name}`)));
      container.appendChild(btn);
    });
  } catch (e) {
    container.innerHTML = `<span class='muted'>unavailable: ${e.message}</span>`;
  }
}

// ---------- actions ----------

async function runAction(button, action) {
  button.disabled = true;
  try {
    await action();
    refreshDetail();
  } catch (e) {
    toast(e.message, true);
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-interact]");
  if (target && selectedRobot) {
    runAction(target, () =>
      api(`/api/robots/${selectedRobot}/interact/${target.dataset.interact}`, { method: "POST" })
        .then(() => toast(`❤ ${target.dataset.interact}`)));
  }
});

$("#autonomous-toggle").onclick = (event) => {
  const verb = autonomousRunning ? "stop" : "start";
  runAction(event.target, () =>
    api(`/api/robots/${selectedRobot}/autonomous/${verb}`, { method: "POST" })
      .then(() => toast(`Autonomous ${verb}ed`)));
};

$("#behavior-once").onclick = (event) => {
  runAction(event.target, () =>
    api(`/api/robots/${selectedRobot}/behavior`)
      .then((decision) => toast(`🧠 ${decision.behavior}: ${decision.reason}`)));
};

$("#raw-send").onclick = (event) => {
  const command = $("#raw-command").value.trim();
  if (!command) return;
  runAction(event.target, () =>
    api(`/api/robots/${selectedRobot}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    }).then((result) => toast(result.success ? `→ ${command}` : "Command failed", !result.success)));
};

$("#raw-command").addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("#raw-send").click();
});

// ---------- boot ----------

async function tick() {
  try {
    await loadFleet();
    await refreshDetail();
  } catch (e) {
    $("#fleet-stats").textContent = `orchestrator unreachable: ${e.message}`;
  }
}

tick();
refreshTimer = setInterval(tick, REFRESH_MS);
