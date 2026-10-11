/* Mind tab — "What she has learned" (AGENT-18).
 *
 * Agent tool composition: for every goal the agent has tried, the tool
 * combinations, their success rates (with a sparkline of how the rate moved
 * while this page was open) and when each combination was first discovered.
 *
 * Initial load: GET /api/v1/agent/{robot}/tools (the mode's tools; each tool
 * name is also a goal) and GET .../patterns?goal=X for each. Live updates:
 * STOMP /topic/robot/{robot}/learned-patterns, published on every rollup.
 * Without a WebSocket it falls back to reloading every 15 s.
 */
"use strict";

function hlLearnedPatternsCard(container, robotId) {
  const state = { robotId, goals: new Map(), history: new Map(), client: null,
                  subscription: null, timer: null, stopped: false };

  container.innerHTML =
      `<h2>What she has learned <span class="note">agent tool combinations per goal</span></h2>` +
      `<div class="lp-body empty">…</div>` +
      `<h2 style="margin-top:0.8rem">Discovery timeline <span class="note">newest first</span></h2>` +
      `<div class="lp-timeline empty">…</div>`;
  const body = container.querySelector(".lp-body");
  const timeline = container.querySelector(".lp-timeline");

  const key = (goal, combo) => `${goal}|${combo.join("+")}`;

  function remember(goal, patterns, at) {
    state.goals.set(goal, patterns);
    for (const p of patterns) {
      const k = key(goal, p.toolCombination || []);
      const points = state.history.get(k) || [];
      const last = points[points.length - 1];
      if (!last || last.rate !== p.successRate || last.attempts !== p.attempts) {
        points.push({ at, rate: p.successRate, attempts: p.attempts });
        state.history.set(k, points.slice(-30));
      }
    }
  }

  function sparkline(points) {
    if (!points || points.length < 2) return "";
    const w = 80, h = 18;
    const xy = points.map((p, i) =>
        `${(i * w / (points.length - 1)).toFixed(1)},${(h - p.rate * h).toFixed(1)}`);
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="vertical-align:middle">` +
        `<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="${xy.join(" ")}"/></svg>`;
  }

  function pct(rate) {
    return `${Math.round((rate ?? 0) * 100)}%`;
  }

  function render() {
    const goals = [...state.goals.entries()].filter(([, ps]) => ps.length);
    if (!goals.length) {
      body.className = "lp-body empty";
      body.textContent = "nothing learned yet — patterns appear after the agent's first evaluated tool call";
      timeline.className = "lp-timeline empty";
      timeline.textContent = "no patterns discovered yet";
      return;
    }
    body.className = "lp-body";
    body.innerHTML = goals.sort(([a], [b]) => a.localeCompare(b)).map(([goal, patterns]) =>
        `<div class="why-line"><b>${esc(goal)}</b>` +
        patterns.map((p) => {
          const combo = (p.toolCombination || []).join(" → ");
          const trend = sparkline(state.history.get(key(goal, p.toolCombination || [])));
          return `<div class="sub"><span class="mono">${esc(combo)}</span> ` +
              `<span class="pill">${pct(p.successRate)}</span> ` +
              `<span class="muted">${esc(p.successes ?? 0)}/${esc(p.attempts ?? 0)}</span> ` +
              `${trend}</div>`;
        }).join("") + `</div>`).join("");

    const discovered = goals.flatMap(([goal, patterns]) =>
        patterns.map((p) => ({ goal, p })))
        .filter(({ p }) => p.firstDiscovered)
        .sort((a, b) => b.p.firstDiscovered.localeCompare(a.p.firstDiscovered))
        .slice(0, 15);
    timeline.className = discovered.length ? "lp-timeline" : "lp-timeline empty";
    timeline.innerHTML = discovered.length ? discovered.map(({ goal, p }) =>
        `<div class="why-line"><span class="cause mono">` +
        `${esc(new Date(p.firstDiscovered).toLocaleString())}</span> ` +
        `<span class="arrow">→</span> <b>${esc(goal)}</b>: ` +
        `${esc((p.toolCombination || []).join(" → "))}</div>`).join("")
        : "no patterns discovered yet";
  }

  async function load() {
    const base = `/api/v1/agent/${encodeURIComponent(state.robotId)}`;
    try {
      const tools = await hlApi(base, "/tools");
      const goals = new Set((tools || []).map((t) => t.name));
      for (const goal of state.goals.keys()) goals.add(goal);
      const at = Date.now();
      await Promise.all([...goals].map(async (goal) => {
        const patterns = await hlApi(base, `/patterns?goal=${encodeURIComponent(goal)}`);
        remember(goal, Array.isArray(patterns) ? patterns : [], at);
      }));
      render();
    } catch (err) {
      body.className = "lp-body empty";
      body.textContent = `learned patterns unavailable: ${err.message}`;
    }
  }

  function subscribe() {
    if (typeof StompJs === "undefined") return false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    state.client = new StompJs.Client({ brokerURL: `${proto}://${location.host}/ws`,
                                        reconnectDelay: 2000, maxReconnectDelay: 30000 });
    state.client.onConnect = () => {
      state.subscription = state.client.subscribe(
          `/topic/robot/${state.robotId}/learned-patterns`, (message) => {
            const update = JSON.parse(message.body);
            remember(update.goal, update.patterns || [], Date.parse(update.rolledUpAt) || Date.now());
            render();
          });
    };
    state.client.activate();
    return true;
  }

  load();
  if (!subscribe()) state.timer = setInterval(() => { if (hlVisible()) load(); }, 15000);

  return {
    stop() {
      state.stopped = true;
      if (state.timer) clearInterval(state.timer);
      if (state.client) state.client.deactivate();
    },
  };
}
