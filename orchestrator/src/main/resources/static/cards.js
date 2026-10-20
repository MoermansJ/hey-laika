/* Shared cards for the console pages. Each hl*Card(host, base, opts) renders
 * into `host` (a .card or .panel element), polls on its own hlPoll, and
 * returns { refresh, stop }. One implementation per concern: mount the same
 * card wherever it is wanted instead of rewriting it per page.
 *
 *  hlMoodCard      the satellite LED: state, named moods, custom colour
 *  hlSpeakerCard   the Grove Speaker Plus: text-to-speech and the clip library
 *  hlArbiterCard   the behavior arbiter: what runs now, stop, recent runs
 *                  (option why: the event -> binding -> behavior cause chain)
 *  hlQueueStackCard  the per-action feed as a moving column: queued submissions
 *                  on top, the execution line, then finished actions fading
 *                  below. Streams /topic/robot/{id}/actions over STOMP
 *  hlPoseCard      the dead-reckoned pose and the WiFi sniffer's state
 *  hlSensesStrip   one row of live readings: battery, range, signal, mic, satellite
 *  hlConversationCard  "Hey Laika" turns: live state, the last turn, typed input,
 *                  the prompt template and the tool menu (option full)
 *  hlPowerCard     the battery saver: tier, reasons, overrides, thresholds
 */
"use strict";

function hlJsonPost(base, path, body) {
  return hlApi(base, path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

const HL_RAINBOW = "conic-gradient(red, orange, yellow, green, blue, indigo, violet, red)";

function hlSpecCss(spec) {
  if (!spec || spec.effect === "off") return "#222";
  if (spec.effect === "rainbow") return HL_RAINBOW;
  return `rgb(${spec.r}, ${spec.g}, ${spec.b})`;
}

// ---------------------------------------------------------------- mood light

function hlMoodCard(host, base, { title = "Mood light", intervalMs = 2000 } = {}) {
  host.innerHTML =
      `<h2>${esc(title)} <span class="chip mc-chip">…</span></h2>` +
      `<div class="row"><div class="swatch mc-swatch"></div>` +
      `<div><div class="mc-name" style="font-weight:600">—</div>` +
      `<div class="hint mc-detail" style="margin-top:0.1rem"></div></div></div>` +
      `<div class="moods mc-moods"></div>` +
      `<div class="row" style="margin-top:0.5rem">` +
      `<input type="color" class="mc-color" value="#3498db" title="Custom colour">` +
      `<select class="mc-effect"><option value="solid">solid</option>` +
      `<option value="pulse">pulse</option><option value="blink">blink</option></select>` +
      `<label class="small">brightness <input type="range" class="mc-brightness" min="5" max="255" value="255"></label>` +
      `<button class="mc-apply primary">Apply</button><button class="mc-off">Off</button></div>` +
      `<div class="hint">Named moods are what events set on their own (wake phrase, someone in view,` +
      ` leash zones, low battery); pinning one here holds it for a minute over events.` +
      ` The colour picker pins a custom colour.</div>`;
  const q = (sel) => host.querySelector(sel);
  const controls = [".mc-color", ".mc-effect", ".mc-brightness", ".mc-apply", ".mc-off"];
  let rendered = "";

  async function set(body) {
    try { await hlJsonPost(base, "/mood", body); } catch (err) { hlToast(err.message, true); }
    refresh();
  }

  async function refresh() {
    const chip = q(".mc-chip");
    try {
      const m = await hlApi(base, "/mood");
      if (m.palette) hlBadgeState.palette = m.palette;
      if (m.badges) hlBadgeState.badges = m.badges;
      if (!m.enabled) {
        chip.textContent = "no satellite"; chip.className = "chip mc-chip warn";
        q(".mc-detail").textContent = "SATELLITE_HOST not set (or MOOD_ENABLED=false)";
        host.querySelectorAll("button, input, select").forEach((el) => { el.disabled = true; });
        return;
      }
      chip.textContent = m.lastError ? "satellite not answering" : `${m.sets} sets`;
      chip.className = "chip mc-chip " + (m.lastError ? "bad" : "on");
      chip.title = m.lastError || "";
      const c = m.color, level = c.brightness / 255;
      const sw = q(".mc-swatch");
      sw.style.background = c.effect === "off" ? "#222" : c.effect === "rainbow" ? HL_RAINBOW :
          `rgb(${Math.round(c.r * level)}, ${Math.round(c.g * level)}, ${Math.round(c.b * level)})`;
      sw.className = "swatch mc-swatch " + (c.effect === "pulse" || c.effect === "blink" ? c.effect : "");
      sw.style.animationDuration = `${c.periodMs}ms`;
      q(".mc-name").textContent = m.mood.replace("_", " ");
      q(".mc-detail").textContent =
          (m.flash ? `flash, ${m.flash.remainingS}s left, then back to ${m.base} · ` : "") +
          `${c.effect}${c.effect === "pulse" || c.effect === "blink" ? ` ${c.periodMs} ms` : ""}` +
          (m.lastEvent ? ` · last event ${m.lastEvent}` : "");
      const moods = q(".mc-moods");
      const key = (m.moods || []).join(",");
      if (rendered !== key) {
        rendered = key;
        moods.innerHTML = (m.moods || []).map((name) =>
            `<button data-mood="${esc(name)}"><span class="dot" style="background:${hlSpecCss((m.palette || {})[name])}"></span>` +
            `${esc(name.replace("_", " "))}</button>`).join("");
        moods.querySelectorAll("button").forEach((btn) => { btn.onclick = () => set({ mood: btn.dataset.mood }); });
      }
      moods.querySelectorAll("button").forEach((btn) => {
        btn.disabled = false;
        btn.classList.toggle("active", btn.dataset.mood === m.base);
      });
      controls.forEach((sel) => { q(sel).disabled = false; });
    } catch (err) {
      chip.textContent = "mood unavailable"; chip.className = "chip mc-chip bad"; chip.title = err.message;
    }
  }

  q(".mc-apply").onclick = () => {
    const hex = q(".mc-color").value;
    set({ r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16),
          b: parseInt(hex.slice(5, 7), 16), effect: q(".mc-effect").value,
          brightness: Number(q(".mc-brightness").value) });
  };
  q(".mc-off").onclick = () => set({ mood: "off" });
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop };
}

// ------------------------------------------------------------------- speaker

function hlSpeakerCard(host, base, { title = "Speaker", say = true, intervalMs = 5000 } = {}) {
  host.innerHTML =
      `<h2>${esc(title)} <span class="chip sc-chip">…</span></h2>` +
      (say ? `<div class="row"><input type="text" class="sc-text" style="flex:1"` +
             ` placeholder="Say it on the dog (Grove Speaker Plus)" autocomplete="off">` +
             `<button class="sc-say">Speak</button></div>` : "") +
      `<div class="actions sc-sounds" style="margin-top:0.5rem"></div>` +
      `<div class="row sc-voice" style="margin-top:0.5rem">` +
      `<label class="small">voice <select class="sc-voice-id"></select></label>` +
      `<label class="small">variant <select class="sc-variant"></select></label>` +
      `<label class="small">speed <input type="number" class="sc-speed" min="80" max="300" step="10" style="width:4.5rem"> wpm</label>` +
      `<label class="small">pitch <input type="number" class="sc-pitch" min="0" max="99" step="5" style="width:4rem"></label>` +
      `<button class="sc-try" title="Save and say a sample sentence">Try</button>` +
      `<span class="hint sc-engine" style="margin:0"></span></div>` +
      `<div class="hint sc-detail"></div>` +
      `<div class="hint">Clips play on the Grove Speaker Plus on the dog. The volume pot on the` +
      ` speaker is the first thing to check when it sounds wrong.</div>`;
  const q = (sel) => host.querySelector(sel);
  let rendered = "";
  let enabled = false;
  let voicesLoaded = false;

  async function loadVoices() {
    try {
      const v = await hlApi(base, "/mouth/voices");
      const VARIANT_LABELS = { "": "default", m1: "male 1", m2: "male 2", m3: "male 3", m4: "male 4",
        m5: "male 5", m6: "male 6", m7: "male 7", f1: "female 1", f2: "female 2", f3: "female 3",
        f4: "female 4", f5: "female 5", croak: "croak", whisper: "whisper" };
      q(".sc-voice-id").innerHTML = (v.voices || []).map((o) =>
          `<option value="${esc(o.id)}">${esc(o.name)} (${esc(o.id)})</option>`).join("")
          || `<option value="${esc(v.current.voice)}">${esc(v.current.voice)}</option>`;
      q(".sc-variant").innerHTML = (v.variants || [""]).map((x) =>
          `<option value="${esc(x)}">${esc(VARIANT_LABELS[x] ?? x)}</option>`).join("");
      q(".sc-voice-id").value = v.current.voice;
      q(".sc-variant").value = v.current.variant || "";
      q(".sc-speed").value = v.current.speed;
      q(".sc-pitch").value = v.current.pitch;
      // Kokoro and espeak-ng both pick a voice and a speed; variant and pitch
      // are espeak-only knobs Kokoro's TTS call ignores.
      const hasVoices = (v.voices || []).length > 0;
      q(".sc-engine").textContent = hasVoices ? "" : `engine: ${v.engine} (no voice options)`;
      q(".sc-voice-id").disabled = q(".sc-speed").disabled = q(".sc-try").disabled = !hasVoices;
      q(".sc-variant").disabled = q(".sc-pitch").disabled = v.engine !== "espeak-ng";
      voicesLoaded = true;
    } catch (err) {
      q(".sc-engine").textContent = `voices unavailable: ${err.message}`;
    }
  }

  async function saveVoice(preview) {
    q(".sc-try").disabled = true;
    try {
      await hlJsonPost(base, "/mouth/voice", {
        voice: q(".sc-voice-id").value, variant: q(".sc-variant").value,
        speed: Number(q(".sc-speed").value), pitch: Number(q(".sc-pitch").value), preview,
      });
    } catch (err) { q(".sc-detail").textContent = `voice: ${err.message}`; }
    finally { q(".sc-try").disabled = false; refresh(); }
  }
  q(".sc-try").onclick = () => saveVoice(true);
  [".sc-voice-id", ".sc-variant"].forEach((sel) => q(sel).addEventListener("change", () => saveVoice(true)));
  [".sc-speed", ".sc-pitch"].forEach((sel) => q(sel).addEventListener("change", () => saveVoice(false)));

  async function play(sound) {
    try { await hlJsonPost(base, "/mouth/play", { sound }); }
    catch (err) { q(".sc-detail").textContent = `failed: ${err.message}`; }
    refresh();
  }

  async function refresh() {
    const chip = q(".sc-chip");
    try {
      const m = await hlApi(base, "/mouth");
      enabled = !!m.enabled;
      chip.textContent = enabled ? `pin ${m.pin} · ${m.ttsEngine}` : "SPEAKER_PIN not set";
      chip.className = "chip sc-chip " + (enabled ? "on" : "warn");
      q(".sc-detail").textContent = m.error ? `error: ${m.error}`
          : m.text ? `last: "${m.text}" (${m.seconds}s, ${m.chunks} chunks)` : "";
      const sounds = q(".sc-sounds");
      const key = (m.sounds || []).join(",");
      if (rendered !== key) {
        rendered = key;
        sounds.innerHTML = (m.sounds || []).map((s) =>
            `<button data-sound="${esc(s)}">${esc(s.replace(/_/g, " "))}</button>`).join("")
            || `<span class="hint">no clips in dog/sounds</span>`;
        sounds.querySelectorAll("[data-sound]").forEach((btn) => {
          btn.onclick = async () => { btn.disabled = true; await play(btn.dataset.sound); };
        });
      }
      sounds.querySelectorAll("[data-sound]").forEach((btn) => { btn.disabled = !enabled; });
      if (say) q(".sc-say").disabled = !enabled;
      if (!voicesLoaded) await loadVoices();
    } catch (err) {
      chip.textContent = "speaker unavailable"; chip.className = "chip sc-chip warn"; chip.title = err.message;
    }
  }

  if (say) {
    const speak = async () => {
      const text = q(".sc-text").value.trim();
      if (!text) return;
      q(".sc-say").disabled = true;
      try { await hlJsonPost(base, "/mouth/say", { text }); q(".sc-text").value = ""; }
      catch (err) { q(".sc-detail").textContent = `failed: ${err.message}`; }
      finally { q(".sc-say").disabled = false; refresh(); }
    };
    q(".sc-say").onclick = speak;
    q(".sc-text").addEventListener("keydown", (e) => { if (e.key === "Enter") speak(); });
  }
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop, play };
}

// ------------------------------------------------------------------- arbiter

// Which personality mode generated a given cause.type, for causes that
// don't already get a bespoke rendering below. Unlisted types just show
// their raw cause.type, same as before this map existed.
const CAUSE_TYPE_LABEL = {
  "fruitfly": "Fruitfly",
  "nav.target": "Roaming",
  "nav.sweep": "Roaming",
  "nav.override": "Roaming",
  "mode": "Mode switch",
  "voice": "Voice",
};

function hlCauseText(run) {
  const c = run.cause;
  if (!c) return `<span class="cause">${esc(run.source)}</span>`;
  if (c.type === "event") {
    const payload = c.payload ? ` ${esc(JSON.stringify(c.payload))}` : "";
    return `<span class="cause">${esc(c.event)}${payload}</span>` +
        (c.filter ? `<span class="pill">filter ${esc(JSON.stringify(c.filter))}</span>` : "");
  }
  if (c.type === "agent") {
    return `<span class="cause">agent decision${c.decisionId ? " " + esc(c.decisionId) : ""}</span>`;
  }
  const label = CAUSE_TYPE_LABEL[c.type] || c.type;
  return `<span class="cause">${esc(label)}${c.via ? " via " + esc(c.via) : ""}</span>`;
}

function hlArbiterCard(host, base, { title = "Current behavior", runs = 6, why = false, intervalMs = 5000 } = {}) {
  host.innerHTML =
      `<h2>${esc(title)} <span class="chip ac-chip">…</span>` +
      `<button class="ac-stop" style="margin-left:auto" title="Stop the running behavior">Stop</button></h2>` +
      `<div class="ac-current muted">—</div>` +
      `<div class="ac-queue" style="margin-top:0.5rem"></div>` +
      `<div class="ac-runs" style="margin-top:0.5rem"></div>`;
  const q = (sel) => host.querySelector(sel);
  let inFlight = false;

  // Up next: items the arbiter has already accepted but hasn't run yet
  // (bounded, QUEUE_MAX in arbiter.py — currently 10), already sorted by
  // (priority, seq) so array order IS execution order.
  function renderQueue(status) {
    const el = q(".ac-queue");
    const list = status.queued || [];
    if (!list.length) { el.innerHTML = `<span class="empty">nothing queued</span>`; return; }
    el.innerHTML = `<div class="hint" style="margin-bottom:0.2rem">Up next</div>` +
        list.map((item, i) =>
          `<div class="why-line"><span class="pill">#${i + 1}</span> ${hlCauseText(item)} ` +
          `<span class="arrow">→</span> <b>${esc(item.behavior)}</b> ` +
          `<span class="muted">P${item.priority}</span></div>`).join("");
  }

  function renderRuns(status) {
    const list = (status.recentRuns || []).slice(0, runs);
    const el = q(".ac-runs");
    if (!list.length) { el.innerHTML = `<span class="empty">no runs yet</span>`; return; }
    if (why) {
      el.innerHTML = list.map((r) => {
        const preempt = r.preemptedBy
            ? `<span class="pill">preempted by ${r.preemptedBy === "manual_stop" ? "manual stop"
                : "run " + esc(String(r.preemptedBy).slice(0, 8))}</span>` : "";
        return `<div class="why-line">${hlCauseText(r)} <span class="arrow">→</span> ` +
            `<b>${esc(r.behavior)}</b> <span class="status-${esc(r.status)}">${esc(r.status)}</span>${preempt}</div>`;
      }).join("");
      return;
    }
    el.innerHTML = `<table class="data-table"><tr><th>Behavior</th><th>Status</th><th>Source</th><th>Started</th></tr>` +
        list.map((r) => `<tr><td>${esc(r.behavior)}</td><td>${esc(r.status)}</td>` +
            `<td class="muted">${esc(r.source)}</td>` +
            `<td class="muted">${r.startedAt ? new Date(r.startedAt).toLocaleTimeString() : ""}</td></tr>`).join("") +
        `</table>`;
  }

  async function refresh() {
    if (inFlight) return;
    inFlight = true;
    const chip = q(".ac-chip");
    try {
      const status = await hlApi(base, "/arbiter/status");
      const c = status.current;
      const queued = status.queued?.length ? ` · ${status.queued.length} queued` : "";
      chip.textContent = c ? "running" : "idle";
      chip.className = "chip ac-chip " + (c ? "on" : "");
      q(".ac-current").innerHTML = c
          ? `<strong>${esc(c.behavior)}</strong> · step ${c.step}/${c.stepTotal}` +
            ` · <span class="muted">${esc(c.source)}</span> · P${c.priority}${queued}`
          : `idle${queued}`;
      q(".ac-stop").disabled = !c;
      renderQueue(status);
      renderRuns(status);
    } catch (err) {
      chip.textContent = "adapter offline"; chip.className = "chip ac-chip warn"; chip.title = err.message;
    } finally { inFlight = false; }
  }

  q(".ac-stop").onclick = async () => {
    try { await hlApi(base, "/arbiter/stop", { method: "POST" }); }
    catch (err) { hlToast(err.message, true); }
    refresh();
  };
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop };
}

// ------------------------------------------------------------- queue stack

// A vertical stack of cards: queued items (furthest-from-execution at the
// top, next-to-run just above the line), an "execution line" for whatever
// the arbiter is running right now, and the most recently finished run
// trailing below it at reduced opacity. Every card is keyed by runId —
// the SAME id an item carries from submission through to the run log
// (arbiter.py assigns it once, at submit time, in `_enqueue`) — so a
// card's DOM node survives queued -> executing -> done and CSS transitions
// animate the move instead of a hard re-render snap.
function hlQueueStackCard(host, base, { title = "Action queue", intervalMs = 2000,
                                        maxVisible = 12, robotId = null } = {}) {
  host.innerHTML = `<h2>${esc(title)} <span class="chip qs-chip">…</span></h2><div class="qs-stack"></div>`;
  const q = (sel) => host.querySelector(sel);
  const id = robotId || String(base).split("/").filter(Boolean).pop();

  let actions = [];        // newest first, from the per-action feed
  let queued = [];         // submissions the arbiter has accepted but not started
  let live = false;        // true while the STOMP stream is feeding us
  let inFlight = false;
  let client = null, subscription = null;

  const DONE_FADE_STEP = 0.07, DONE_FADE_FLOOR = 0.4;

  // "[FRUITFLY] opk0n - FORWARD": the mode that generated it, the id of that
  // generation, and the action it mapped to.
  function actionLine(a) {
    return `<span class="pill">[${esc(a.tag || "?")}]</span>` +
        `<span class="muted">${esc(a.id)}</span> <span class="arrow">-</span> ` +
        `<b>${esc(a.action)}</b>`;
  }

  function queuedCardHtml(item, position) {
    return `<span class="pill">#${position}</span> ${hlCauseText(item)} ` +
        `<span class="arrow">→</span> <b>${esc(item.behavior)}</b> ` +
        `<span class="muted">P${item.priority}</span>`;
  }

  function execCardHtml(a) {
    return `<span class="qs-badge">EXECUTING</span> ${actionLine(a)}` +
        (a.command && a.command !== a.action
            ? ` <span class="muted">${esc(a.command)}</span>` : "");
  }

  function doneCardHtml(a) {
    return `${actionLine(a)} <span class="status-${esc(a.status)}">${esc(a.status)}</span>`;
  }

  function render() {
    const stackEl = q(".qs-stack");
    const visible = actions.slice(0, maxVisible);
    // The feed's newest entry is the step being dispatched right now; it sits
    // on the execution line and everything already finished stacks below it,
    // fading as it moves down and out.
    const running = visible.length && visible[0].status === "executing" ? visible[0] : null;
    const done = running ? visible.slice(1) : visible;

    // Pending submissions ride above the line, furthest-out on top.
    const entries = queued.slice(0, maxVisible).map((item, i) => ({
      key: item.runId || `q-${i}`, cls: "qs-queued", html: queuedCardHtml(item, i + 1),
    })).reverse();

    entries.push({
      key: running ? running.id : "qs-idle",
      cls: "qs-execline " + (running ? "qs-active" : "qs-idle"),
      html: running ? execCardHtml(running)
          : `<span class="empty">idle — nothing executing</span>`,
    });

    done.forEach((a, i) => {
      entries.push({
        key: a.id, cls: "qs-done", html: doneCardHtml(a),
        opacity: Math.max(DONE_FADE_FLOOR, 0.8 - i * DONE_FADE_STEP),
      });
    });

    // Keyed reuse: an action keeps its feed id for its whole life, so the same
    // DOM node carries it from the execution line down through the trail and
    // the FLIP below animates that move instead of redrawing the column.
    const existing = new Map();
    stackEl.querySelectorAll("[data-key]").forEach((el) => existing.set(el.dataset.key, el));
    // Measure with offsetTop, NOT getBoundingClientRect: entries arrive about
    // once a second and the slide below runs for 0.4s, so a rect read can
    // land mid-animation and return the TRANSFORMED position, which then
    // compounds into drifting, floating cards. offsetTop is the layout
    // position and ignores the transform entirely.
    const firstTops = new Map();
    existing.forEach((el, key) => firstTops.set(key, el.offsetTop));

    const frag = document.createDocumentFragment();
    entries.forEach((e) => {
      let el = existing.get(String(e.key));
      const isNew = !el;
      if (!el) { el = document.createElement("div"); el.dataset.key = String(e.key); }
      el.className = "qs-card " + e.cls + (isNew ? " qs-enter" : "");
      el.innerHTML = e.html;
      el.style.opacity = e.opacity != null ? String(e.opacity) : "";
      frag.appendChild(el);
    });
    stackEl.innerHTML = "";
    stackEl.appendChild(frag);

    requestAnimationFrame(() => {
      existing.forEach((el, key) => {
        if (!el.isConnected) return;
        const dy = firstTops.get(key) - el.offsetTop;
        if (Math.abs(dy) < 1) return;
        el.style.transition = "none";
        el.style.transform = `translateY(${dy}px)`;
        requestAnimationFrame(() => { el.style.transition = ""; el.style.transform = ""; });
      });
    });

    const chip = q(".qs-chip");
    chip.textContent = running ? (live ? "live" : "polling") : (live ? "idle · live" : "idle");
    chip.className = "chip qs-chip " + (running ? "on" : "");
  }

  // ---- transports: STOMP for the actions, a slow poll for the rest -------

  async function refresh({ actionsToo = true } = {}) {
    if (inFlight) return;
    inFlight = true;
    try {
      const status = await hlApi(base, "/arbiter/status");
      const nextQueued = status.queued || [];
      const queuedChanged = JSON.stringify(nextQueued.map((item) => item.runId))
          !== JSON.stringify(queued.map((item) => item.runId));
      queued = nextQueued;
      // While the socket is feeding us, actions arrive push-side; only pull
      // them when it is down (or on the first load, to fill the stack).
      let actionsChanged = false;
      if (actionsToo || !live) {
        const feed = await hlApi(base, `/actions/feed?limit=${maxVisible}`);
        actions = feed.actions || [];
        actionsChanged = true;
      }
      // Don't re-render (and re-animate) just because the poll came round:
      // under STOMP the stream already drew the newest state.
      if (queuedChanged || actionsChanged) render();
    } catch (err) {
      const chip = q(".qs-chip");
      chip.textContent = "adapter offline";
      chip.className = "chip qs-chip warn";
      chip.title = err.message;
    } finally { inFlight = false; }
  }

  function connectStomp() {
    if (typeof StompJs === "undefined" || !id) return;   // poll-only fallback
    const proto = location.protocol === "https:" ? "wss" : "ws";
    client = new StompJs.Client({
      brokerURL: `${proto}://${location.host}/ws`,
      reconnectDelay: 1000,
      maxReconnectDelay: 30000,
    });
    client.onConnect = () => {
      live = true;
      if (subscription) subscription.unsubscribe();
      subscription = client.subscribe(`/topic/robot/${id}/actions`, (message) => {
        try {
          actions = (JSON.parse(message.body) || {}).actions || [];
          render();
        } catch { /* a malformed frame shouldn't kill the stream */ }
      });
    };
    client.onWebSocketClose = () => { live = false; subscription = null; };
    client.activate();
  }

  connectStomp();
  const poller = hlPoll(refresh, intervalMs);
  return {
    refresh,
    stop: () => {
      poller.stop();
      if (subscription) { subscription.unsubscribe(); subscription = null; }
      if (client) { client.deactivate(); client = null; }
      live = false;
    },
  };
}

// ---------------------------------------------------------------------- pose

function hlPoseCard(host, base, { title = "Where she thinks she is", intervalMs = 10000 } = {}) {
  host.innerHTML = `<h2>${esc(title)}</h2><div class="pc-body empty">…</div>`;
  const body = host.querySelector(".pc-body");

  function render(s) {
    const p = s && s.pose;
    if (!p) { body.className = "pc-body empty"; body.textContent = "no pose yet"; return; }
    const last = s.lastSample;
    const age = s.lastSniffAgeS != null ? `${Math.round(s.lastSniffAgeS)} s ago` : "not yet this session";
    body.className = "pc-body";
    body.innerHTML =
        `<div class="stat"><span>Last known position</span><span class="mono">${p.x}, ${p.y} m</span></div>` +
        `<div class="stat"><span>Heading</span><span>${p.heading}°</span></div>` +
        `<div class="stat"><span>Dead-reckoning uncertainty</span><span>±${p.driftM} m</span></div>` +
        `<div class="stat"><span>Last sniff</span><span>${esc(age)}</span></div>` +
        `<div class="stat"><span>Last sample</span><span>${last ? esc(new Date(last.t * 1000).toLocaleString()) : "—"}</span></div>` +
        `<div class="stat"><span>Sniffer</span><span>${s.away ? "suppressed (away)" : s.enabled ? "listening for motion gaps" : "off"}</span></div>` +
        `<div class="stat"><span>Stored samples</span><span>${s.sampleCount ?? 0}</span></div>`;
  }

  async function refresh() {
    try { render(await hlApi(base, "/senses")); }
    catch (err) { body.className = "pc-body empty"; body.textContent = `senses unavailable: ${err.message}`; }
  }
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop, render };
}

// -------------------------------------------------------------- senses strip

function hlSensesStrip(host, base, { intervalMs = 3000 } = {}) {
  const cells = [
    { key: "battery", name: "Battery", unit: "%" },
    { key: "range", name: "Range ahead", unit: "cm" },
    { key: "signal", name: "WiFi to router", unit: "dBm" },
    { key: "mic", name: "Mic level", unit: "rms" },
    { key: "satellite", name: "Satellite WiFi", unit: "dBm" },
  ];
  host.innerHTML = `<div class="strip">` + cells.map((c) =>
      `<div class="sensor na" data-cell="${c.key}" title="${esc(c.name)}"><div class="name">${esc(c.name)}</div>` +
      `<div class="value"><span class="v">…</span> <span class="unit">${esc(c.unit)}</span></div></div>`).join("") +
      `</div>`;
  const cell = (key) => host.querySelector(`[data-cell="${key}"]`);

  function show(key, value, note) {
    const el = cell(key);
    el.classList.toggle("na", value == null);
    el.querySelector(".v").textContent = value == null ? "n/a" : value;
    el.title = note || el.querySelector(".name").textContent;
  }

  async function refresh() {
    const [status, range, leash, ears, sat] = await Promise.allSettled([
      hlApi(base, "/status"), hlApi(base, "/senses/range"), hlApi(base, "/leash"),
      hlApi(base, "/ears"), hlApi(base, "/satellite"),
    ]);
    const v = (r) => (r.status === "fulfilled" ? r.value : null);
    const s = v(status), r = v(range), l = v(leash), e = v(ears), d = v(sat)?.device;
    show("battery", s?.battery != null ? Math.round(s.battery) : null, s ? "Battery estimate from pack voltage" : "adapter offline");
    show("range", r ? (r.distanceCm == null ? "no echo" : Math.round(r.distanceCm)) : null,
        r ? `pin ${r.pin} · ${r.reads} reads, ${r.misses} misses` : "ULTRASONIC_PIN not set or adapter offline");
    show("signal", l?.rssi != null ? Math.round(l.rssi) : null, l ? `${l.ssid || "?"} · zone ${l.zone}` : "no leash data");
    show("mic", e?.level ? e.level.rms : null, e ? `1 s peak ${e.level?.peak} · floor ${e.level?.floor}${e.level?.speaking ? " · gate open" : ""}` : "no satellite stream");
    show("satellite", d?.rssi ?? null, d ? `up ${Math.round((d.uptimeS || 0) / 60)} min · mic ${d.mic ? "ok" : "off"} · camera ${d.camera ? "ok" : "off"}` : "satellite offline");
  }
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop };
}

// -------------------------------------------------------------- conversation

function hlConversationCard(host, base, { title = "Conversation", full = false, intervalMs = 1000 } = {}) {
  host.innerHTML =
      `<h2>${esc(title)} <span class="cc-state"></span>` +
      `<button class="cc-listen" style="margin-left:auto" title="Start a turn as if the wake phrase had been heard: sit, listen, answer">Listen</button>` +
      `<button class="cc-cancel" title="Stop speaking and go back to idle">Cancel</button></h2>` +
      `<div class="row"><input type="text" class="cc-text" style="flex:1" autocomplete="off"` +
      ` placeholder="Type what you would say after “Hey Laika” — same router, same speaker"><button class="cc-say primary">Send</button></div>` +
      `<div class="cc-current hint"></div>` +
      `<div class="cc-turns" style="margin-top:0.5rem"></div>` +
      (full ? `<details class="cc-settings" style="margin-top:0.6rem"><summary class="hint" style="cursor:pointer;margin:0">Prompt and tools</summary>` +
              `<label class="hint" style="display:block;margin:0.4rem 0 0.2rem">Prompt template (<code>%s</code> is the transcript; a brevity instruction is appended)</label>` +
              `<textarea class="cc-prompt" spellcheck="false" style="min-height:4.5rem"></textarea>` +
              `<div class="row" style="margin-top:0.3rem"><label class="small">reply cap <input type="number" class="cc-cap" min="40" max="2000" step="20"> chars</label>` +
              `<button class="cc-save">Save</button><span class="hint cc-saved" style="margin:0"></span></div>` +
              `<div class="hint cc-tools"></div>` +
              `<label class="hint" style="display:block;margin:0.6rem 0 0.2rem">Introduction — what she says to “Hey Laika, introduce yourself”. The orchestrator stores it and pushes it to her.</label>` +
              `<textarea class="cc-intro" spellcheck="false" style="min-height:4.5rem"></textarea>` +
              `<div class="row" style="margin-top:0.3rem"><button class="cc-intro-save">Save introduction</button>` +
              `<span class="hint cc-intro-saved" style="margin:0"></span></div></details>` : "") +
      `<div class="hint">“Hey Laika” alone: she sits, the LED pulses green while she listens, purple while the LLM thinks, teal while she speaks.` +
      ` The LLM picks one tool from the bindings on <code>voice.intent</code> or answers in one or two sentences.</div>`;
  const q = (sel) => host.querySelector(sel);
  const STATE_BADGE = { listening: "listening", thinking: "thinking", speaking: "speaking" };
  let promptLoaded = false, promptDirty = false;

  async function post(path, body) {
    try { await hlJsonPost(base, path, body); } catch (err) { hlToast(err.message, true); }
    refresh();
  }

  // The introduction lives on the orchestrator (Postgres), not in the adapter's
  // /conversation status, so it is fetched once rather than on every poll.
  async function loadIntroduction() {
    try {
      const intro = await hlApi(base, "/conversation/introduction");
      q(".cc-intro").value = intro.text || "";
      q(".cc-intro-saved").textContent = intro.text
          ? `stored ${intro.updatedBy ? `by ${intro.updatedBy}` : ""}`.trim()
          : "nothing stored — she is speaking the adapter's built-in text";
    } catch (err) {
      q(".cc-intro-saved").textContent = `could not load: ${err.message}`;
    }
  }

  function renderTurns(turns) {
    const el = q(".cc-turns");
    if (!turns.length) { el.innerHTML = `<span class="empty">no turns yet</span>`; return; }
    el.innerHTML = `<table class="data-table"><tr><th>When</th><th>Heard</th><th>Did</th><th>Said</th><th>Latency</th></tr>` +
        turns.map((t) => {
          const did = t.error ? `<span style="color:var(--critical)">${esc(t.error)}</span>`
              : t.tool && t.tool !== "answer" ? hlBadge("wake", t.tool) : (t.tool ? "answered" : "—");
          const lat = [t.whisperS != null ? `ears ${t.whisperS}s` : null, t.llmS != null ? `llm ${t.llmS}s` : null,
                       t.speakS != null ? `speak ${t.speakS}s` : null].filter(Boolean).join(" · ");
          return `<tr><td class="muted">${new Date(t.at).toLocaleTimeString()}</td><td>${esc(t.heard || "")}</td>` +
              `<td>${did}</td><td>${esc(t.said || "")}</td><td class="muted">${lat}</td></tr>`;
        }).join("") + `</table>`;
  }

  async function refresh() {
    try {
      const c = await hlApi(base, `/conversation?limit=${full ? 10 : 5}`);
      const badge = STATE_BADGE[c.state];
      q(".cc-state").innerHTML = !c.enabled ? `<span class="chip warn">disabled</span>`
          : badge ? hlBadge(badge, c.state) : `<span class="chip">idle</span>`;
      q(".cc-cancel").disabled = c.state === "idle";
      q(".cc-listen").disabled = c.state !== "idle";
      q(".cc-say").disabled = c.state !== "idle";
      const cur = c.current;
      q(".cc-current").textContent = cur
          ? `${c.state} for ${cur.elapsedS}s${cur.heard ? ` · heard “${cur.heard}”` : ""}${cur.tool ? ` · tool ${cur.tool}` : ""}${cur.said ? ` · saying “${cur.said}”` : ""}`
          : `${c.turns.length ? "" : "say “Hey Laika” or type below · "}${c.tools.length} tools · ${c.turns.length} recent turns`;
      renderTurns(c.turns || []);
      if (full) {
        if (!promptLoaded || !promptDirty) {
          q(".cc-prompt").value = c.prompt || "";
          q(".cc-cap").value = c.replyChars || 320;
          promptLoaded = true;
        }
        q(".cc-tools").innerHTML = `tools from the bindings on voice.intent: ` +
            (c.tools.map((t) => `<b>${esc(t.name)}</b> → ${esc(t.behavior)}`).join(", ") || "none") +
            `, plus <b>answer</b>. Add a binding on the Behavior tab to add a voice command.`;
      }
    } catch (err) {
      q(".cc-state").innerHTML = `<span class="chip warn" title="${esc(err.message)}">unavailable</span>`;
    }
  }

  const send = () => {
    const text = q(".cc-text").value.trim();
    if (!text) return;
    q(".cc-text").value = "";
    post("/conversation/say", { text });
  };
  q(".cc-say").onclick = send;
  q(".cc-text").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
  q(".cc-listen").onclick = () => post("/conversation/listen");
  q(".cc-cancel").onclick = () => post("/conversation/cancel");
  if (full) {
    [".cc-prompt", ".cc-cap"].forEach((sel) => q(sel).addEventListener("input", () => { promptDirty = true; }));
    q(".cc-save").onclick = async () => {
      try {
        await hlJsonPost(base, "/conversation/prompt",
            { prompt: q(".cc-prompt").value, replyChars: Number(q(".cc-cap").value) });
        promptDirty = false;
        q(".cc-saved").textContent = `saved ${new Date().toLocaleTimeString()}`;
      } catch (err) { q(".cc-saved").textContent = `failed: ${err.message}`; }
      refresh();
    };
    q(".cc-intro-save").onclick = async () => {
      try {
        const saved = await hlJsonPost(base, "/conversation/introduction",
            { introduction: q(".cc-intro").value });
        q(".cc-intro-saved").textContent =
            `saved and pushed ${new Date().toLocaleTimeString()} · ${saved.text.length} chars`;
      } catch (err) { q(".cc-intro-saved").textContent = `failed: ${err.message}`; }
    };
    loadIntroduction();
  }
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop };
}

// -------------------------------------------------------------- battery saver

function hlPowerCard(host, base, { title = "Battery saver", intervalMs = 5000 } = {}) {
  const TIER_HELP = {
    active: "everything on",
    eco: "camera 1 fps, LED dimmed, WiFi sniffer off",
    doze: "lying down, servos off, camera paused, LED at 10 %",
    critical: "servos off at safety priority, motion refused until charged",
  };
  const FIELDS = [
    ["ecoPct", "eco below %"], ["dozePct", "doze below %"], ["criticalPct", "critical below %"],
    ["hysteresisPct", "hysteresis %"], ["ecoIdleS", "eco after quiet s"], ["dozeIdleS", "doze after quiet s"],
    ["ecoFps", "eco camera fps"], ["ecoLedDim", "eco LED (0-1)"], ["dozeLedDim", "doze LED (0-1)"],
    ["stationaryAfterS", "stationary after s"], ["sensorsWhenStationary", "sensors while still (0/1)"],
  ];
  host.innerHTML =
      `<h2>${esc(title)} <span class="pw-tier"></span><span class="hint pw-since" style="margin:0"></span>` +
      `<span class="row" style="margin-left:auto">` +
      `<button class="pw-auto" title="Let the saver decide from battery and quiet time">Auto</button>` +
      `<button class="pw-active" title="Wake her up and hold active">Wake</button>` +
      `<button class="pw-eco" title="Hold eco">Eco</button>` +
      `<button class="pw-doze" title="Hold doze: lie down, servos off">Doze</button></span></h2>` +
      `<div class="hint pw-detail"></div>` +
      `<div class="strip pw-tiers" style="margin-top:0.5rem"></div>` +
      `<details style="margin-top:0.6rem"><summary class="hint" style="cursor:pointer;margin:0">Thresholds</summary>` +
      `<div class="row pw-fields" style="margin-top:0.4rem"></div>` +
      `<div class="row" style="margin-top:0.4rem"><button class="pw-save">Save</button><span class="hint pw-saved" style="margin:0"></span></div></details>` +
      `<div class="hint">Sensors follow motion: the camera, the ranger and the WiFi sniffer run while she moves and pause` +
      ` once she has been still for the stationary time; the ears and the speaker never pause.` +
      ` Anything that shows someone is there wakes her: a wake phrase, a person in view, a leash event,` +
      ` being lifted, a command from the console. A battery-forced tier lifts only once the level climbs back above the` +
      ` threshold plus the hysteresis band, or on Wake.</div>`;
  const q = (sel) => host.querySelector(sel);
  q(".pw-fields").innerHTML = FIELDS.map(([key, label]) =>
      `<label class="small">${esc(label)} <input type="number" step="any" data-key="${key}" style="width:5.5rem"></label>`).join("");
  let fieldsLoaded = false, dirty = false;
  host.querySelectorAll(".pw-fields input").forEach((el) => el.addEventListener("input", () => { dirty = true; }));

  const TIER_BADGE = { active: "online", eco: "warn", doze: "person", critical: "lowBattery" };

  async function post(path, body) {
    try { await hlJsonPost(base, path, body); } catch (err) { hlToast(err.message, true); }
    refresh();
  }

  async function refresh() {
    try {
      const p = await hlApi(base, "/power/saver");
      q(".pw-tier").innerHTML = hlBadge(TIER_BADGE[p.tier] || "warn", p.tier + (p.manual ? " · held" : ""));
      q(".pw-since").textContent = `for ${Math.round(p.sinceS)} s` + (p.reasons.length ? ` · ${p.reasons.join(", ")}` : "");
      const sensors = p.config.sensorsWhenStationary ? "sensors always on"
          : p.moving ? `moving${p.motionS != null ? ` (${Math.round(p.motionS)} s ago)` : ""}: camera, ranger, sniffer on`
          : `stationary${p.motionS != null ? ` ${Math.round(p.motionS)} s` : ""}: camera, ranger, sniffer paused; ears and speaker on`;
      q(".pw-detail").textContent =
          `${TIER_HELP[p.tier] || ""} · ${sensors} · battery ${p.battery != null ? Math.round(p.battery) + " %" : "unknown"}` +
          ` · quiet ${Math.round(p.idleS)} s (last activity: ${p.lastActivity})` +
          ` · ${p.transitions} transitions, ${p.wakes} wakes${p.enabled ? "" : " · DISABLED (POWER_SAVER_ENABLED)"}`;
      q(".pw-tiers").innerHTML = p.tiers.map((t) =>
          `<div class="sensor${t === p.tier ? "" : " na"}"><div class="name">${esc(t)}</div>` +
          `<div class="value" style="font-size:0.75rem">${esc(TIER_HELP[t] || "")}</div></div>`).join("");
      ["auto", "active", "eco", "doze"].forEach((k) => {
        const btn = q(`.pw-${k}`);
        btn.classList.toggle("active", k === "auto" ? !p.manual : p.manual === k);
      });
      if (!fieldsLoaded || !dirty) {
        host.querySelectorAll(".pw-fields input").forEach((el) => { el.value = p.config[el.dataset.key]; });
        fieldsLoaded = true;
      }
    } catch (err) {
      q(".pw-tier").innerHTML = `<span class="chip warn" title="${esc(err.message)}">unavailable</span>`;
    }
  }

  q(".pw-auto").onclick = () => post("/power/saver", { tier: null });
  q(".pw-active").onclick = () => post("/power/saver", { tier: "active" });
  q(".pw-eco").onclick = () => post("/power/saver", { tier: "eco" });
  q(".pw-doze").onclick = () => post("/power/saver", { tier: "doze" });
  q(".pw-save").onclick = async () => {
    const body = {};
    host.querySelectorAll(".pw-fields input").forEach((el) => { body[el.dataset.key] = Number(el.value); });
    try {
      await hlJsonPost(base, "/power/saver/config", body);
      dirty = false; q(".pw-saved").textContent = `saved ${new Date().toLocaleTimeString()}`;
    } catch (err) { q(".pw-saved").textContent = `failed: ${err.message}`; }
    refresh();
  };
  const poller = hlPoll(refresh, intervalMs);
  return { refresh, stop: poller.stop };
}
