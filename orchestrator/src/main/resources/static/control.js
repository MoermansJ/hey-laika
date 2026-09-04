/* Control Panel — schema-driven manual control.
 * Renders sliders/actions/sensors from GET /capabilities, so nothing about
 * the servo count or limits is hardcoded here. Servo POSTs are coalesced:
 * the firmware drops commands that arrive while it is executing one, so we
 * keep a single in-flight move and send only the latest desired state next. */
"use strict";

const GROUP_LABELS = {
  head: "Head",
  leg_fl: "Front Left Leg", leg_fr: "Front Right Leg",
  leg_bl: "Back Left Leg", leg_br: "Back Right Leg",
};
const READBACK_INTERVAL_MS = 2000;

const $ = (sel) => document.querySelector(sel);

const state = {
  robots: [],
  robotId: null,
  servos: [],            // schema order
  actions: [],
  sensors: [],
  metadata: {},
  targets: new Map(),    // index -> angle the user wants
  pending: new Map(),    // index -> angle queued while a move is in flight
  inFlight: false,
  dragging: null,        // servo index currently being dragged
  actionUntil: 0,        // timestamp until which action buttons stay disabled
  autonomyRunning: false,
};

// ---------- helpers ----------

function toast(message, isError) {
  const el = $("#toast");
  el.textContent = message;
  el.className = isError ? "err" : "";
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.style.display = "none"; }, 2500);
}

async function api(path, options) {
  const res = await fetch(`/api/robots/${state.robotId}${path}`, options);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message = body?.message || body?.error || `HTTP ${res.status}`;
    throw Object.assign(new Error(message), { status: res.status });
  }
  return body;
}

// ---------- servo moves (coalesced single-flight) ----------

function queueMove(index, angle) {
  state.targets.set(index, angle);
  state.pending.set(index, angle);
  pump();
}

async function pump() {
  if (state.inFlight || state.pending.size === 0) return;
  const joints = [...state.pending.entries()]
      .map(([index, angle]) => ({ index, angle }));
  state.pending.clear();
  state.inFlight = true;
  try {
    const result = await api("/servo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ joints }),
    });
    if (result.clamped) toast("Angle clamped to safe limits");
  } catch (err) {
    if (err.status === 409) {
      state.autonomyRunning = true;
      renderAutonomyChip();
      toast("Blocked: stop autonomous mode first", true);
    } else {
      toast(`Move failed: ${err.message}`, true);
    }
  } finally {
    state.inFlight = false;
    if (state.pending.size > 0) pump();   // send whatever arrived meanwhile
  }
}

// ---------- readback ----------

async function pollReadback() {
  if (state.inFlight || !state.robotId) return;
  try {
    const stateResp = await api("/servo");
    const chip = $("#readback-chip");
    chip.textContent = "readback: live";
    chip.classList.add("on");
    for (const joint of stateResp.joints) {
      const row = document.querySelector(`[data-servo="${joint.index}"]`);
      if (!row) continue;
      row.querySelector(".actual").textContent = `fw ${joint.angle}°`;
      // Don't yank a slider out of the user's hand; otherwise follow firmware.
      if (state.dragging !== joint.index && !state.targets.has(joint.index)) {
        row.querySelector("input").value = joint.angle;
        row.querySelector(".target").textContent = `${joint.angle}°`;
      }
    }
  } catch {
    const chip = $("#readback-chip");
    chip.textContent = "readback: unavailable";
    chip.classList.remove("on");
  }
}

async function refreshAutonomy() {
  // The adapter's in-process autonomous loop is deprecated (behavior
  // framework owns motion); only the orchestrator loop is worth polling.
  state.autonomyRunning = false;
  try {
    const behavior = await api("/behavior/status");
    state.behaviorLoopRunning = behavior.running;
  } catch { state.behaviorLoopRunning = false; }
  renderAutonomyChip();
}

function renderAutonomyChip() {
  const chip = $("#autonomy-chip");
  if (state.autonomyRunning) {
    chip.style.display = "";
    chip.textContent = "adapter autonomy on";
    chip.title = "Manual servo control returns 409 while the adapter's autonomous loop runs";
  } else if (state.behaviorLoopRunning) {
    chip.style.display = "";
    chip.textContent = "behavior loop driving robot";
    chip.title = "The orchestrator's behavior loop is executing actions on the hardware — " +
        "stop it in Behavior Lab before manual posing, or your slider moves will be overridden";
  } else {
    chip.style.display = "none";
  }
  chip.className = "chip warn";
}

// ---------- rendering ----------

function renderServos() {
  const container = $("#servo-groups");
  container.innerHTML = "";
  const groups = new Map();
  for (const servo of state.servos) {
    if (!groups.has(servo.group)) groups.set(servo.group, []);
    groups.get(servo.group).push(servo);
  }
  for (const [group, servos] of groups) {
    const section = document.createElement("div");
    section.className = "servo-group";
    section.innerHTML = `<h3>${esc(GROUP_LABELS[group] ?? group)}</h3>`;
    for (const servo of servos) {
      const row = document.createElement("div");
      row.className = "servo-row";
      row.dataset.servo = servo.index;
      const min = Number(servo.min), max = Number(servo.max);
      row.innerHTML =
          `<div class="head"><span class="sname" title="${esc(servo.description)}">` +
          `${esc(servo.displayName)} <span style="color:var(--muted)">#${Number(servo.index)}</span></span>` +
          `<span class="sval"><span class="target">—</span> <span class="actual"></span></span></div>` +
          `<input type="range" min="${min}" max="${max}" step="1" value="0"` +
          ` aria-label="${esc(servo.displayName)} angle">` +
          `<div class="range-labels"><span>${min}°</span><span>0°</span><span>${max}°</span></div>`;
      const slider = row.querySelector("input");
      const target = row.querySelector(".target");
      slider.addEventListener("pointerdown", () => { state.dragging = servo.index; });
      slider.addEventListener("input", () => { target.textContent = `${slider.value}°`; });
      slider.addEventListener("change", () => {
        state.dragging = null;
        queueMove(servo.index, Number(slider.value));
      });
      section.appendChild(row);
    }
    container.appendChild(section);
  }
}

function renderActions() {
  const container = $("#actions");
  container.innerHTML = "";
  const byCategory = new Map();
  for (const action of state.actions) {
    if (!byCategory.has(action.category)) byCategory.set(action.category, []);
    byCategory.get(action.category).push(action);
  }
  for (const [category, actions] of byCategory) {
    const label = document.createElement("div");
    label.className = "cat";
    label.textContent = category;
    container.appendChild(label);
    for (const action of actions) {
      const btn = document.createElement("button");
      btn.dataset.action = action.id;
      btn.innerHTML = `${esc(action.displayName)}` +
          (action.verified ? "" : ` <span class="unverified" title="Not yet verified on this firmware">*</span>`) +
          `<span class="dur">${(Number(action.durationMs) / 1000).toFixed(1)}s</span>`;
      btn.onclick = () => runAction(action);
      container.appendChild(btn);
    }
  }
}

async function runAction(action) {
  state.actionUntil = Date.now() + action.durationMs;
  setActionsDisabled(true);
  setTimeout(() => {
    if (Date.now() >= state.actionUntil) setActionsDisabled(false);
  }, action.durationMs + 100);
  try {
    const result = await api("/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: action.id }),
    });
    if (!result.success) toast(`${action.displayName}: no completion echo`, true);
    state.targets.clear();   // a skill re-poses everything; trust readback again
  } catch (err) {
    toast(`${action.displayName} failed: ${err.message}`, true);
    setActionsDisabled(false);
  }
}

function setActionsDisabled(disabled) {
  document.querySelectorAll("#actions button").forEach((b) => { b.disabled = disabled; });
  $("#btn-balance").disabled = disabled;
  $("#btn-rest").disabled = disabled;
}

function renderSensors() {
  $("#sensors").innerHTML = state.sensors.map((sensor) =>
      `<div class="sensor ${sensor.available ? "" : "na"}" title="${esc(sensor.description)}">` +
      `<div class="name">${esc(sensor.displayName)}</div>` +
      `<div class="value">${sensor.available ? "…" : "n/a"}` +
      ` <span class="unit">${sensor.available ? esc(sensor.unit) : ""}</span></div></div>`).join("");
}

function renderMeta() {
  const m = state.metadata;
  $("#meta").innerHTML =
      `Firmware <b>${esc(m.firmwareVersion ?? "unknown")}</b> · model <b>${esc(m.model ?? "—")}</b>` +
      ` · transport <b>${esc(m.mode ?? "—")}</b> · ${Number(m.servoCount) || "?"} servos` +
      ` · calibrated: <b>${m.calibrated ? "yes" : "no"}</b>`;
  const chip = $("#mode-chip");
  chip.textContent = m.mode ?? "…";
  chip.className = "chip " + (m.mode === "mock" ? "warn" : "on");
  chip.title = m.mode === "mock"
      ? "Adapter is in mock mode — no hardware will move" : "";
}

// ---- peripherals: speaker clips and the mood light (satellite LED) ----

const LED_PREVIEW = {
  off: "#000", idle: "#ff8c28", heard: "#0078ff", thinking: "#a000ff", speaking: "#00ffaa",
  happy: "#00ff28", person: "#00d2ff", alert: "#ffa000", warn: "#ff5a00", lost: "#ff0000",
  low_battery: "#ff0000",
  rainbow: "conic-gradient(red, orange, yellow, green, blue, indigo, violet, red)",
};

async function refreshSpeaker() {
  const chip = $("#speaker-chip");
  try {
    const m = await api("/mouth");
    chip.textContent = m.enabled ? `pin ${m.pin}` : "SPEAKER_PIN not set";
    chip.className = "chip " + (m.enabled ? "on" : "warn");
    const host = $("#speaker-sounds");
    const key = (m.sounds || []).join(",");
    if (host.dataset.rendered !== key) {
      host.dataset.rendered = key;
      host.innerHTML = (m.sounds || []).map((s) =>
          `<button data-dog-sound="${esc(s)}">${esc(s.replace(/_/g, " "))}</button>`).join("")
          || `<span class="hint">no clips in dog/sounds</span>`;
      host.querySelectorAll("[data-dog-sound]").forEach((btn) => btn.onclick = async () => {
        btn.disabled = true;
        try {
          await api("/mouth/play", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sound: btn.dataset.dogSound }) });
          toast(`Playing ${btn.dataset.dogSound.replace(/_/g, " ")}`);
        } catch (err) { toast(err.message, true); }
        finally { btn.disabled = !m.enabled; }
      });
    }
    host.querySelectorAll("[data-dog-sound]").forEach((btn) => btn.disabled = !m.enabled);
  } catch { chip.textContent = "unavailable"; chip.className = "chip warn"; }
}

async function setLed(body) {
  try {
    await api("/mood", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });
  } catch (err) { toast(err.message, true); }
  refreshLed();
}

async function refreshLed() {
  const chip = $("#led-chip");
  try {
    const m = await api("/mood");
    const enabled = m.enabled;
    chip.textContent = !enabled ? "no satellite" : m.lastError ? "satellite not answering"
        : `${m.mood.replace("_", " ")}${m.flash ? ` (flash, then ${m.base})` : ""}`;
    chip.className = "chip " + (!enabled ? "warn" : m.lastError ? "off" : "on");
    const host = $("#led-moods");
    const key = (m.moods || []).join(",");
    if (host.dataset.rendered !== key) {
      host.dataset.rendered = key;
      host.innerHTML = (m.moods || []).map((name) =>
          `<button data-mood="${esc(name)}"><span style="display:inline-block;width:0.65rem;height:0.65rem;border-radius:50%;margin-right:0.35rem;border:1px solid rgba(0,0,0,0.15);background:${LED_PREVIEW[name] || "#888"}"></span>${esc(name.replace("_", " "))}</button>`).join("");
      host.querySelectorAll("[data-mood]").forEach((btn) => btn.onclick = () => setLed({ mood: btn.dataset.mood }));
    }
    host.querySelectorAll("[data-mood]").forEach((btn) => {
      btn.disabled = !enabled;
      btn.classList.toggle("active", btn.dataset.mood === m.base);
    });
    ["#led-apply", "#led-off", "#led-color", "#led-effect"].forEach((sel) => $(sel).disabled = !enabled);
  } catch { chip.textContent = "unavailable"; chip.className = "chip warn"; }
}

function bindLedControls() {
  $("#led-apply").onclick = () => {
    const hex = $("#led-color").value;
    setLed({ r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16),
             b: parseInt(hex.slice(5, 7), 16), effect: $("#led-effect").value });
  };
  $("#led-off").onclick = () => setLed({ mood: "off" });
}

async function refreshBattery() {
  const chip = $("#battery-chip");
  try {
    const status = await api("/status");
    if (status.battery == null) { chip.style.display = "none"; return; }
    chip.style.display = "";
    chip.textContent = `${Math.round(status.battery)}%`;
    chip.className = "chip " + (status.battery < 20 ? "warn" : "on");
    chip.title = "Battery estimate from pack voltage";
  } catch { chip.style.display = "none"; }
}

// ---------- boot ----------
// (Voice simulation moved to voice.html — the robot page's Voice tab.)

async function loadRobot() {
  const caps = await api("/capabilities");
  state.servos = caps.schema.servos;
  state.actions = caps.schema.actions;
  state.sensors = caps.schema.sensors;
  state.metadata = caps.metadata ?? {};
  state.targets.clear();
  state.pending.clear();
  renderServos();
  renderActions();
  renderSensors();
  renderMeta();
  await refreshAutonomy();
  await pollReadback();
}

function bindTopbar() {
  $("#robot-select").onchange = async (event) => {
    state.robotId = event.target.value;
    await startRobot();
  };
  const pinned = (id, fallbackMs) => () => {
    const action = state.actions.find((a) => a.id === id) ??
        { id, displayName: id, durationMs: fallbackMs };
    runAction(action);
  };
  $("#btn-balance").onclick = pinned("kbalance", 1000);
  $("#btn-rest").onclick = pinned("krest", 2000);
}

let pollers = [];

async function startRobot() {
  pollers.forEach((p) => p.stop());
  pollers = [];
  try {
    await loadRobot();
  } catch (err) {
    // Adapter down (502 adapter_unavailable) or schema fetch failed: say
    // so and offer a retry instead of sitting on "loading schema…".
    toast(`Cannot load ${state.robotId}: ${err.message}`, true);
    hlRetryBlock($("#servo-groups"), `Adapter unavailable: ${err.message}`, startRobot);
    return;
  }
  await refreshBattery();
  pollers.push(hlPoll(pollReadback, READBACK_INTERVAL_MS, { immediate: false }));
  pollers.push(hlPoll(refreshAutonomy, 5000, { immediate: false }));
  // Matches the adapter's telemetry cache TTL — polling faster returns
  // the same cached reading anyway.
  pollers.push(hlPoll(refreshBattery, 20000, { immediate: false }));
  pollers.push(hlPoll(refreshSpeaker, 15000));
  pollers.push(hlPoll(refreshLed, 3000));
}

async function boot() {
  let robots;
  try {
    robots = await hlApi("", "/api/fleet/robots");
  } catch (err) {
    hlRetryBlock($("#servo-groups"), `Orchestrator unreachable: ${err.message}`, boot);
    return;
  }
  state.robots = robots;
  $("#robot-select").innerHTML = robots.map((r) =>
      `<option value="${esc(r.robotId)}">${esc(r.name)}</option>`).join("");
  // Embedded as a robot-page tab: the parent says which robot this is.
  // Falling back to robots[0] here once drove Laika from Mocha's page.
  const wanted = hlRobotParam(null);
  state.robotId = robots.some((r) => r.robotId === wanted)
      ? wanted : robots[0]?.robotId;
  if (!state.robotId) return;
  $("#robot-select").value = state.robotId;
  bindLedControls();
  bindTopbar();
  await startRobot();
}

boot();
