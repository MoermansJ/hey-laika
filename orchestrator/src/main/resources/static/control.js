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
  metadata: {},
  cards: [],             // shared cards mounted for the current robot
  targets: new Map(),    // index -> angle the user wants
  pending: new Map(),    // index -> angle queued while a move is in flight
  inFlight: false,
  dragging: null,        // servo index currently being dragged
  actionUntil: 0,        // timestamp until which action buttons stay disabled
  autonomyRunning: false,
};

// ---------- helpers ----------

const toast = hlToast;
const api = (path, options) => hlApi(`/api/robots/${state.robotId}`, path, options);

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

// ---------- boot ----------
// (Voice simulation moved to voice.html — the robot page's Voice tab.)

async function loadRobot() {
  const caps = await api("/capabilities");
  state.servos = caps.schema.servos;
  state.actions = caps.schema.actions;
  state.metadata = caps.metadata ?? {};
  state.targets.clear();
  state.pending.clear();
  renderServos();
  renderActions();
  renderMeta();
  await refreshAutonomy();
  await pollReadback();
}

function bindTopbar() {
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
  state.cards.forEach((card) => card.stop());
  state.cards = [];
  try {
    await loadRobot();
  } catch (err) {
    // Adapter down (502 adapter_unavailable) or schema fetch failed: say
    // so and offer a retry instead of sitting on "loading schema…".
    toast(`Cannot load ${state.robotId}: ${err.message}`, true);
    hlRetryBlock($("#servo-groups"), `Adapter unavailable: ${err.message}`, startRobot);
    return;
  }
  pollers.push(hlPoll(pollReadback, READBACK_INTERVAL_MS, { immediate: false }));
  pollers.push(hlPoll(refreshAutonomy, 5000, { immediate: false }));
  const base = `/api/robots/${state.robotId}`;
  state.cards.push(hlSensesStrip($("#senses-strip"), base));
  state.cards.push(hlMoodCard($("#mood-card"), base));
}

async function boot() {
  let page;
  try {
    page = await hlPage({ onRobotChange: async (id) => { state.robotId = id; await startRobot(); } });
  } catch (err) {
    hlRetryBlock($("#servo-groups"), `Orchestrator unreachable: ${err.message}`, boot);
    return;
  }
  state.robots = page.robots;
  state.robotId = page.robotId;
  if (!state.robotId) return;
  bindTopbar();
  await startRobot();
}

boot();
