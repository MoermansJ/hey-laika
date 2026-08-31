/* Sequence Builder — drag-and-drop movement timeline.
 * Palette comes from GET /capabilities (schema.movements); playback sends each
 * block sequentially through POST /execute_action, which completes only when
 * the firmware finishes the motion — so awaiting each call IS the timeline. */
"use strict";

const PX_PER_SEC = 60;
const CATEGORY_ORDER = ["posture", "gait", "head", "trick"];
const STORE_KEY = "bittle-sequences";

const $ = (sel) => document.querySelector(sel);

const state = {
  robotId: null,
  movements: [],            // schema movements
  byId: new Map(),
  blocks: [],               // {id, durationMs}
  selected: null,           // index
  playing: false,
  stopRequested: false,
  loopRunning: false,
  dragFrom: null,           // timeline index being dragged, or null (palette)
};

function toast(message, isError) {
  const el = $("#toast");
  el.textContent = message;
  el.className = isError ? "err" : "";
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.style.display = "none"; }, 2600);
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

// ---------- palette ----------

function renderPalette() {
  const palette = $("#palette");
  palette.innerHTML = "";
  for (const category of CATEGORY_ORDER) {
    const movements = state.movements.filter((m) => m.category === category);
    if (!movements.length) continue;
    const label = document.createElement("div");
    label.className = "cat-label";
    label.textContent = category;
    palette.appendChild(label);
    for (const movement of movements) {
      const block = document.createElement("div");
      block.className = "pal-block";
      block.style.setProperty("--c", `var(--c-${movement.category})`);
      block.draggable = true;
      block.innerHTML = `${movement.displayName}` +
          `<span class="dur">${(movement.defaultDurationMs / 1000).toFixed(1)}s</span>`;
      block.addEventListener("dragstart", (event) => {
        state.dragFrom = null;
        event.dataTransfer.setData("text/plain", movement.id);
        event.dataTransfer.effectAllowed = "copy";
      });
      // Click-to-append fallback (mobile / no-drag).
      block.addEventListener("dblclick", () => {
        state.blocks.push({ id: movement.id, durationMs: movement.defaultDurationMs });
        renderTimeline();
      });
      palette.appendChild(block);
    }
  }
}

// ---------- timeline ----------

function blockWidth(durationMs) {
  return Math.max(64, (durationMs / 1000) * PX_PER_SEC);
}

function renderRuler() {
  const total = totalMs();
  const seconds = Math.max(8, Math.ceil(total / 1000) + 2);
  const ruler = $("#ruler");
  ruler.innerHTML = "";
  for (let s = 0; s < seconds; s++) {
    const tick = document.createElement("span");
    tick.style.width = `${PX_PER_SEC}px`;
    tick.textContent = `${s}s`;
    ruler.appendChild(tick);
  }
}

function totalMs() {
  return state.blocks.reduce((sum, b) => sum + b.durationMs, 0);
}

function renderTimeline() {
  const timeline = $("#timeline");
  timeline.innerHTML = "";
  if (!state.blocks.length) {
    timeline.innerHTML =
        `<span class="tl-empty">drag movements here — drag blocks to reorder</span>`;
    state.selected = null;
  }
  state.blocks.forEach((block, index) => {
    const movement = state.byId.get(block.id);
    const el = document.createElement("div");
    el.className = "tl-block" + (index === state.selected ? " selected" : "");
    el.dataset.index = index;
    el.style.width = `${blockWidth(block.durationMs)}px`;
    el.style.setProperty("--c", `var(--c-${movement?.category ?? "posture"})`);
    el.draggable = !state.playing;
    el.innerHTML = `<span class="bname">${movement?.displayName ?? block.id}</span>` +
        `<span class="bdur">${(block.durationMs / 1000).toFixed(1)}s</span>`;
    el.addEventListener("click", () => selectBlock(index));
    el.addEventListener("dragstart", (event) => {
      state.dragFrom = index;
      event.dataTransfer.setData("text/plain", block.id);
      event.dataTransfer.effectAllowed = "move";
    });
    timeline.appendChild(el);
  });
  renderRuler();
  renderInspector();
  $("#total-chip").textContent = `${(totalMs() / 1000).toFixed(1)} s`;
  $("#btn-play").disabled = state.playing || state.loopRunning || !state.blocks.length;
}

function insertionIndex(event) {
  const blocks = [...$("#timeline").querySelectorAll(".tl-block")];
  for (let i = 0; i < blocks.length; i++) {
    const rect = blocks[i].getBoundingClientRect();
    if (event.clientX < rect.left + rect.width / 2) return i;
  }
  return blocks.length;
}

function clearCaret() {
  $("#timeline").querySelectorAll(".drop-caret").forEach((c) => c.remove());
}

function bindTimelineDnD() {
  const timeline = $("#timeline");
  timeline.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (state.playing) return;
    timeline.classList.add("dragover");
    clearCaret();
    const index = insertionIndex(event);
    const caret = document.createElement("div");
    caret.className = "drop-caret";
    const blocks = timeline.querySelectorAll(".tl-block");
    if (index >= blocks.length) timeline.appendChild(caret);
    else timeline.insertBefore(caret, blocks[index]);
  });
  timeline.addEventListener("dragleave", (event) => {
    if (event.target === timeline) { timeline.classList.remove("dragover"); clearCaret(); }
  });
  timeline.addEventListener("drop", (event) => {
    event.preventDefault();
    timeline.classList.remove("dragover");
    clearCaret();
    if (state.playing) return;
    let index = insertionIndex(event);
    const movementId = event.dataTransfer.getData("text/plain");
    if (state.dragFrom !== null) {
      const [moved] = state.blocks.splice(state.dragFrom, 1);
      if (index > state.dragFrom) index--;
      state.blocks.splice(index, 0, moved);
      state.selected = index;
    } else {
      const movement = state.byId.get(movementId);
      if (!movement) return;
      state.blocks.splice(index, 0,
          { id: movement.id, durationMs: movement.defaultDurationMs });
      state.selected = index;
    }
    state.dragFrom = null;
    renderTimeline();
  });
}

// ---------- inspector ----------

function selectBlock(index) {
  state.selected = index;
  renderTimeline();
}

function renderInspector() {
  const inspector = $("#inspector");
  if (state.selected === null || !state.blocks[state.selected]) {
    inspector.style.display = "none";
    return;
  }
  const block = state.blocks[state.selected];
  const movement = state.byId.get(block.id);
  inspector.style.display = "";
  $("#insp-name").textContent = movement?.displayName ?? block.id;
  $("#insp-dur").value = block.durationMs;
  $("#insp-val").textContent = `${(block.durationMs / 1000).toFixed(1)} s`;
}

function bindInspector() {
  $("#insp-dur").addEventListener("input", (event) => {
    const block = state.blocks[state.selected];
    if (!block) return;
    block.durationMs = Number(event.target.value);
    $("#insp-val").textContent = `${(block.durationMs / 1000).toFixed(1)} s`;
    const el = $("#timeline").querySelector(`[data-index="${state.selected}"]`);
    if (el) {
      el.style.width = `${blockWidth(block.durationMs)}px`;
      el.querySelector(".bdur").textContent = `${(block.durationMs / 1000).toFixed(1)}s`;
    }
    $("#total-chip").textContent = `${(totalMs() / 1000).toFixed(1)} s`;
    renderRuler();
  });
  $("#insp-remove").onclick = removeSelected;
  document.addEventListener("keydown", (event) => {
    if (event.key === "Delete" && state.selected !== null
        && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      removeSelected();
    }
  });
}

function removeSelected() {
  if (state.selected === null || state.playing) return;
  state.blocks.splice(state.selected, 1);
  state.selected = null;
  renderTimeline();
}

// ---------- playback ----------

async function play() {
  if (state.playing || !state.blocks.length) return;
  state.playing = true;
  state.stopRequested = false;
  $("#btn-play").disabled = true;
  $("#btn-stop").disabled = false;
  const blockEls = [...$("#timeline").querySelectorAll(".tl-block")];
  try {
    for (let i = 0; i < state.blocks.length; i++) {
      if (state.stopRequested) { toast("Stopped"); break; }
      const block = state.blocks[i];
      blockEls.forEach((el, j) => {
        el.classList.toggle("playing", j === i);
        el.classList.toggle("played", j < i);
      });
      const result = await api("/execute_action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: block.id, durationMs: block.durationMs,
                               sequenceId: i }),
      });
      if (!result.success) {
        toast(`${block.id} failed: ${result.message}`, true);
        break;
      }
    }
  } catch (err) {
    toast(err.status === 409 ? "Blocked: stop the behavior loop first"
                             : `Playback failed: ${err.message}`, true);
  } finally {
    state.playing = false;
    $("#btn-stop").disabled = true;
    blockEls.forEach((el) => el.classList.remove("playing", "played"));
    renderTimeline();
  }
}

// ---------- library (localStorage) ----------

function library() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) ?? {}; }
  catch { return {}; }
}

function renderLibrary() {
  const names = Object.keys(library()).sort();
  $("#seq-list").innerHTML = names.map((n) => `<option>${n}</option>`).join("");
}

function bindLibrary() {
  $("#btn-save").onclick = () => {
    const name = $("#seq-name").value.trim();
    if (!name) { toast("Name the sequence first", true); return; }
    if (!state.blocks.length) { toast("Timeline is empty", true); return; }
    const lib = library();
    lib[name] = state.blocks;
    localStorage.setItem(STORE_KEY, JSON.stringify(lib));
    renderLibrary();
    $("#seq-list").value = name;
    toast(`Saved “${name}”`);
  };
  $("#btn-load").onclick = () => {
    const name = $("#seq-list").value;
    const sequence = library()[name];
    if (!sequence) return;
    state.blocks = sequence.map((b) => ({ ...b }));
    state.selected = null;
    $("#seq-name").value = name;
    renderTimeline();
  };
  $("#btn-delete").onclick = () => {
    const name = $("#seq-list").value;
    if (!name) return;
    const lib = library();
    delete lib[name];
    localStorage.setItem(STORE_KEY, JSON.stringify(lib));
    renderLibrary();
    toast(`Deleted “${name}”`);
  };
  $("#btn-clear").onclick = () => {
    if (state.playing) return;
    state.blocks = [];
    state.selected = null;
    renderTimeline();
  };
}

// ---------- loop guard ----------

async function refreshLoopChip() {
  try {
    const status = await api("/behavior/status");
    state.loopRunning = status.running;
  } catch { state.loopRunning = false; }
  $("#loop-chip").style.display = state.loopRunning ? "" : "none";
  if (!state.playing) {
    $("#btn-play").disabled = state.loopRunning || !state.blocks.length;
  }
}

// ---------- boot ----------

async function boot() {
  const robots = await (await fetch("/api/fleet/robots")).json();
  $("#robot-select").innerHTML = robots.map((r) =>
      `<option value="${r.robotId}">${r.name}</option>`).join("");
  state.robotId = robots[0]?.robotId;
  if (!state.robotId) return;
  $("#robot-select").onchange = (event) => { state.robotId = event.target.value; };

  const caps = await api("/capabilities");
  state.movements = caps.schema.movements ?? [];
  state.byId = new Map(state.movements.map((m) => [m.id, m]));

  renderPalette();
  renderTimeline();
  renderLibrary();
  bindTimelineDnD();
  bindInspector();
  bindLibrary();
  $("#btn-play").onclick = play;
  $("#btn-stop").onclick = () => { state.stopRequested = true; };
  await refreshLoopChip();
  setInterval(refreshLoopChip, 4000);
}

boot();
