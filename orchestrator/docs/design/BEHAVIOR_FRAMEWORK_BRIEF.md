# Planning Brief — Behavior Framework for Laika

**Date:** 2026-08-31 · **Status:** planning input, written for the planning agent
**Goal:** one coherent framework that combines *lifecycle events* with *actions an
agent invokes*, replacing today's scattered behavior sources with a single
arbitrated system the host fully owns.

---

## 1. Why now

The firmware reset (Phase A, flashed & validated) made the robot a **silent,
honest machine**: no reflex motion, no silent command drops, exceptions are
*reported* to the host instead of acted on. All personality has moved host-side —
but it moved as **independent, uncoordinated pieces**. The framework's job is to
unify them.

### Current behavior sources (the inventory to unify)

| Source | Where | Trigger | Conflict handling today |
|---|---|---|---|
| Boot greeting | `dog/app/greeting.py` | controller `on_online` callback | debounce only |
| Idle ladder (sit→lie) | `dog/app/idle_keeper.py` | no motion command for 60s/120s | ad-hoc `suppressed()` lambda checking other drivers |
| Orchestrator behavior loop | `orchestrator/.../behavior/*` (rule-based decision engine, 2.5s reflex cycle, 15-action catalog) | personality state | 409s against manual servo moves |
| Adapter autonomous loop | `dog/app/app.py` autonomous | interval timer | deprecated old brain; blocks execute_action |
| Gait learner | `dog/app/gait_learner.py` | API sessions | others must not run; idle keeper checks its state |
| Manual GUI / raw commands | Control tab, choreography, `/command` | human | none — races possible |
| Voice demo | Voice tab → Ollama | simulated speech | none (motion side is beeps only today) |

**The problem in one sentence:** there is no single owner of the robot's motion —
suppression is pairwise and ad-hoc, and adding the next behavior source (the
Claude director, scheduled behaviors, exception responses) multiplies the mess.

---

## 2. The framework concept

Three first-class notions:

### 2.1 Behavior = named, declarative sequence (data, not code)

Exactly what the greeting already is internally, promoted to stored data:

```json
{
  "name": "startup_greeting",
  "description": "Go-mode announcement when Laika comes online",
  "steps": [
    {"command": "kup",              "settleS": 2.5},
    {"command": "kstr",             "settleS": 5.0},
    {"command": "kup",              "settleS": 2.0},
    {"command": "b 14 8 18 8 21 8 26 4", "settleS": 1.5},
    {"command": "kbalance",         "settleS": 2.0}
  ],
  "interruptible": true,
  "cooldownS": 60
}
```

- Step vocabulary: raw firmware commands first; later step types for higher
  primitives we already own (`feedback_turn: {deg}`, `goto: {x,y}` from the gait
  learner; `say: {prompt}` via Ollama; `sound: {pattern}`).
- Stored in the adapter (SQLite alongside existing models), CRUD via API,
  **edited visually by resurrecting the Sequence Builder** (`builder.html` is
  unlisted but intact on disk — its drag-and-drop output is precisely a step
  list; repoint its save/play targets from choreography to behaviors).
- Built-ins (`startup_greeting`, `idle_sit`, `idle_rest`) ship as seed rows,
  user-editable like any other.

### 2.2 Trigger = lifecycle event bound to a behavior

| Event | Source (already emitting today) | Example binding |
|---|---|---|
| `robot.online` | controller `on_online` | → startup_greeting |
| `robot.offline` | connect failure | → (GUI alert; no motion) |
| `idle.threshold` (parameterized) | idle keeper clock | 60s → idle_sit, 120s → idle_rest |
| `battery.level` (25/15/5%) | voltage telemetry (cached `P` reads) | → tired_animation + warning beeps |
| `imu.exception` | firmware `EXCEPTION_REPORT <code> yaw…` lines (Cut #3) | flipped → host-decided recovery (the "tier-2" reflex, now programmable!) |
| `voice.phrase` | future: voice module WS event | → behavior per phrase |
| `schedule` | cron-like | bedtime lie-down, morning stretch |
| `agent.invoke` | the Claude director / behavior loop | → any behavior or ad-hoc step list |
| `manual` | GUI/API | → any behavior |

Bindings are data too: `{event, filter, behaviorName, priority}` — a settings
page can rewire "what happens when" without code.

### 2.3 Arbiter = the single motion owner

One executor in the **adapter** (closest to the hardware lock) through which ALL
motion flows. Suggested priority ladder, highest first:

1. **safety** — host-decided exception responses, low-battery rest
2. **manual** — human at the GUI / direct API
3. **agent** — Claude director / orchestrator behavior loop decisions
4. **lifecycle** — greeting, scheduled behaviors, battery warnings
5. **idle** — the sit/lie ladder (lowest; anything preempts it)

Rules the planner should specify precisely:
- Higher priority **preempts** lower (interruptible behaviors stop at the next
  step boundary; a preempted idle posture is simply abandoned).
- Equal/lower priority **queues or is rejected** (bounded queue, explicit
  `busy` responses — never silent).
- Every transition is an event: activity log + STOMP topic
  (`/topic/robot/{id}/behavior` already exists) so the GUI can show "current
  behavior: startup_greeting (step 3/5, source: lifecycle)".
- The gait learner and servo sliders become arbiter clients too (manual
  priority), retiring today's pairwise 409/suppression checks.

---

## 3. Constraints the design must respect (hard-won, all validated live)

- **Driver rules** (`docs/reports/CALIBRATION_2026-08-31.md`): interleave `kup`
  between bounded gaits; `kwk*`/skill completion echoes are immediate on the WS
  — steps need wall-clock settle times until firmware Phase B lands; `g*` polls
  are gait-safe; stand/lie transitions rotate the body 12–25°.
- **Firmware Phase B is the big unlock** (`docs/design/FIRMWARE_RESET.md` cuts
  5/8/9): motion-end completion frames would let the executor drop settle
  timers for true event-driven stepping. Design the step executor so
  `settleS` becomes optional once completion frames exist.
- **Voltage gating:** below ~6.9V precision motion is meaningless and the pack
  is at risk — the arbiter should refuse/degrade non-safety behaviors (telemetry
  is already cached adapter-side).
- **2-client WS cap** on the robot: the adapter stays the sole motion channel;
  the framework must never spawn a second command connection.
- **Exception responses are motion too:** a "flipped → self-right" behavior runs
  through the same arbiter at safety priority — that's the whole point of
  having removed the firmware reflex.

---

## 4. Assets to reuse (don't rebuild these)

| Asset | Reuse as |
|---|---|
| `greeting.py` / `idle_keeper.py` | first two framework clients — refactor their triggers into event bindings, their sequences into stored behaviors |
| `builder.html` + `builder.js` (unlisted) | the behavior editor GUI |
| `choreography.py` animations, `action_executor.py` plans, `robot_schema.py` catalog | step vocabulary / palette entries for the builder |
| Gait learner `_turn_by` (gyro-feedback turns), `_goto` (dead-reckon to point) | high-level step types |
| Orchestrator `BehaviorService` / `RuleBasedDecisionEngine` / STOMP broadcast | the "agent" client (and later the Claude director — personality Phase 2) submits through the arbiter instead of calling `execute_action` directly |
| Greeting/idle proxy routes in `RobotController` | pattern for framework API passthrough |

---

## 5. Suggested phasing

- **Phase 1 — Arbiter + stored behaviors (adapter):** executor with priority
  ladder; behavior/binding storage + CRUD API; greeting and idle refactored as
  clients; orchestrator proxy routes; GUI "current behavior" indicator.
- **Phase 2 — Builder GUI:** resurrect the Sequence Builder as the behavior
  editor (palette from schema/choreography, save/load/test against the arbiter);
  bindings settings page.
- **Phase 3 — Event expansion:** battery thresholds, EXCEPTION_REPORT parsing
  (adapter must start reading unsolicited WS/serial lines), schedules,
  host-decided fall recovery as a safety behavior.
- **Phase 4 — Agent integration:** the Claude director invokes behaviors and
  ad-hoc step lists through the arbiter with clear interruption semantics;
  personality loop migrates from direct `execute_action` to arbiter client.
- **(Parallel/optional)** firmware Phase B for event-driven stepping.

## 6. Open questions for the planner

1. Where does behavior state live long-term — adapter SQLite (per robot) vs
   orchestrator Postgres (fleet-wide library synced down)? (Lean: adapter owns
   execution truth, orchestrator owns the shared library.)
2. Preemption granularity: step boundary only, or mid-step abort with a
   guaranteed `kup` recovery step?
3. Should the orchestrator behavior loop's 15-action catalog become behaviors
   in the same store (single vocabulary), or stay a separate reflex layer?
4. Trigger conditions language: fixed filter fields per event, or a tiny
   expression language (battery < 15 AND time > 22:00)?
5. How do multi-robot fleets share behaviors (Laika's greeting vs robot #2's)?

**References:** `docs/design/FIRMWARE_RESET.md`, `docs/reports/CALIBRATION_2026-08-31.md`,
`docs/reports/PLANNER_HANDOFF_CALIBRATION.md`, `docs/robot/` (hardware, firmware
capabilities, network API), memory of live-validated behavior in
`dog/app/{greeting,idle_keeper,gait_learner}.py`.
