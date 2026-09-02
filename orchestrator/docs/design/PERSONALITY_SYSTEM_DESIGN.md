# BITTLE AUTONOMOUS PERSONALITY SYSTEM - DESIGN DOCUMENT

**Version:** 1.1
**Date:** August 2026
**Status:** Phase 1 in progress
**Architecture:** Java Spring Boot Orchestrator (Brain) → Python Flask Adapter (Body)

**Changes vs v1.0 (review outcome):**

- Decided the architecture conflict: the orchestrator owns the brain; the Python
  adapter is stripped to dumb execution. Its existing `/personality`, `/behavior`,
  `/autonomous/*` and `/interact/*` endpoints are deprecated (§2.3).
- Claude is no longer called per action. A rule-based reflex loop runs every
  cycle; Claude acts as a low-frequency "director" (§5).
- Model changed from `claude-opus-4-5` to `claude-haiku-4-5`; free-text response
  parsing replaced by API-enforced structured outputs (§5.3).
- Posture is tracked as first-class state; actions declare required and
  resulting postures and invalid actions are filtered before any decision (§3.4, §4).
- Sensor contract corrected to the real base Bittle X V2 hardware: 6-axis IMU,
  back touch sensor, microphone. No distance/LiDAR/camera (§7).
- SLEEP impact defined; energy model made internally consistent (§6).
- REST paths unified under `/api/robots/{robotId}/behavior/**` (§8).
- Manual actions are coordinated with the autonomous loop via a queue (§4.3).
- Design is per-robot (fleet of N), loops managed per `RobotAgent` (§2.2).
- Dashboard integration rides the existing STOMP broadcaster (§8.3).
- Python adapter work added to the roadmap (§10).

---

## 1. EXECUTIVE SUMMARY

Each Bittle robot runs with an internal personality state (energy, happiness,
boredom, curiosity, hunger for attention, contentment) plus a physical posture.
The orchestrator maintains this state per robot and drives autonomous behavior
from it. Decisions are two-tier: a cheap rule-based reflex loop picks the next
action every few seconds, while Claude is consulted at a much lower cadence to
set direction ("mood"/behavior bias). The Python adapter translates high-level
actions into servo commands and reports real sensor feedback (IMU, touch).

**Key decision:** the orchestrator is the single brain. The Python adapter's
legacy personality/autonomy endpoints are deprecated and will be removed.

---

## 2. SYSTEM ARCHITECTURE

### 2.1 High-Level Flow

```
┌────────────────────────────────────────────────────────────┐
│        JAVA SPRING BOOT ORCHESTRATOR (Brain)               │
│                                                            │
│  Per robot (managed by BehaviorService / FleetManager):    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ RobotBehaviorLoop                                   │  │
│  │  ├─ PersonalityState (incl. posture)                │  │
│  │  ├─ Reflex loop: every ~2.5s                        │  │
│  │  │   1. filter actions valid for current posture    │  │
│  │  │   2. DecisionEngine picks action                 │  │
│  │  │   3. ActionExecutor → adapter HTTP call          │  │
│  │  │   4. PersonalityStateManager applies deltas      │  │
│  │  │   5. publish behavior event (STOMP)              │  │
│  │  ├─ Director (Phase 2): Claude call every ~45s      │  │
│  │  │   or on significant state change / owner event   │  │
│  │  └─ Manual action queue (dashboard/API commands)    │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
                        ↓ REST (PythonServiceClient)
┌────────────────────────────────────────────────────────────┐
│     PYTHON FLASK ADAPTER (Body — execution only)           │
│                                                            │
│  POST /api/robots/{id}/execute_action                      │
│   ├─ map action → Petoi skill/servo commands               │
│   ├─ execute movement                                      │
│   └─ return { success, actualDurationMs, sensorFeedback }  │
│                                                            │
│  Sensor events (touch, IMU) pushed/polled → orchestrator   │
└────────────────────────────────────────────────────────────┘
                        ↓ Serial/WiFi
              Bittle X V2 Hardware (servos, IMU, touch, mic)
```

### 2.2 Fleet Scope

Everything in this design is **per robot**. `BehaviorService` owns one
`RobotBehaviorLoop` per registered `RobotAgent` (from `FleetManager`). Loops
start on demand (API/config flag), not automatically at boot, so a robot can be
driven manually without the autonomous brain fighting it. Claude cost scales
with robot count — another reason for the low-frequency director design.

### 2.3 Adapter Migration

The adapter currently exposes its own `/personality`, `/behavior`,
`/autonomous/start|stop|status` and `/interact/{type}` endpoints — a second
brain. Migration plan:

1. Adapter gains `POST /api/robots/{id}/execute_action` (dumb execution).
2. Orchestrator behavior system ships and becomes the only decision maker.
3. Adapter's personality/behavior/autonomous/interact endpoints and their
   backing logic are removed; orchestrator proxies (`RobotAgent.personality()`,
   `nextBehavior()`, `startAutonomous()` etc.) are removed with them, and the
   dashboard switches to the orchestrator's `/behavior/**` API and topics.

Until step 3 completes, the adapter's autonomous mode must not run while an
orchestrator behavior loop is active for the same robot.

---

## 3. PERSONALITY STATE MODEL

### 3.1 Dimensions

All personality values are doubles in **[0.0, 1.0]** internally. Any
presentation as percentages happens at the edge (prompt building, UI), never in
the model.

| Field | 0.0 | 1.0 |
|---|---|---|
| energy | exhausted/asleep | hyperactive |
| happiness | sad/lonely | ecstatic |
| boredom | fully entertained | extremely bored |
| curiosity | indifferent | intensely curious |
| hunger (for attention) | satisfied | desperately seeking interaction |
| contentment | very dissatisfied | perfectly content |

Metadata: `lastAction`, `lastActionAt`, `lastInteractionAt`,
`totalActionsThisSession`, and **`posture`** (§3.4).

### 3.2 Constraints

- Clipped to [0.0, 1.0] after every update.
- State persists across cycles; passive decay/growth applies per cycle.
- External events (owner interaction, sensor events) cause step changes.

### 3.3 Initial State

```
energy 0.6, happiness 0.7, boredom 0.4, curiosity 0.5,
hunger 0.3, contentment 0.6, posture STANDING
```

### 3.4 Posture

```
enum Posture { STANDING, SITTING, LYING, SLEEPING }
```

- Each action declares which postures it can start from and which posture it
  leaves the robot in.
- The decision engine (rule-based *and* Claude) only ever chooses from actions
  valid for the current posture — prerequisites are enforced structurally, not
  by hoping the model respects them.
- Assumed posture can later be verified against IMU orientation (§7); a
  mismatch (e.g. picked up, fell over) triggers a re-sync event.

---

## 4. ACTION SYSTEM

### 4.1 Action Catalog

Actions are a Java enum carrying their full definition (id, estimated duration,
required postures, resulting posture, personality impact):

| Action | Duration | From posture | To posture |
|---|---|---|---|
| WALK_SLOW | 3000ms | STANDING | STANDING |
| WALK_FAST | 2000ms | STANDING | STANDING |
| STAND_UP | 1000ms | SITTING, LYING | STANDING |
| SIT_DOWN | 1500ms | STANDING | SITTING |
| LIE_DOWN | 2000ms | STANDING, SITTING | LYING |
| LOOK_LEFT / LOOK_RIGHT / LOOK_UP | 800ms | STANDING, SITTING | unchanged |
| PLAY_BOW | 1500ms | STANDING | STANDING |
| BACKFLIP | 2000ms | STANDING | STANDING |
| SPIN | 2000ms | STANDING | STANDING |
| IDLE_CALM | 1000ms | any awake | unchanged |
| SLEEP | 5000ms | LYING | SLEEPING |
| WAKE_UP | 1000ms | SLEEPING | LYING |
| SEEK_ATTENTION | 2000ms | STANDING, SITTING | unchanged |

Notes:
- `WAKE_UP` is new — SLEEPING is a real posture and needs an exit.
- BACKFLIP is gated on `energy > 0.5` (hardware safety) in addition to posture.

### 4.2 Scheduling

The loop is strictly sequential per robot: decide → execute (blocking HTTP,
duration ≈ action duration) → update → wait. The effective cycle time is
`actionDuration + decisionIntervalMs`; the "2–3s" interval is the *pause
between actions*, not a hard cycle rate. While the robot SLEEPs, decisions
still run (so it can wake) but at a slower cadence.

### 4.3 Manual Actions

`POST /api/robots/{id}/behavior/action/{action}` enqueues a manual action on
the loop's queue. The loop drains manual actions **before** making autonomous
decisions, so manual control and autonomy never race on the servos. Each
executed action carries a `sequenceId` so adapter-side logs correlate. When the
loop is stopped, manual actions execute immediately.

---

## 5. DECISION ENGINE

### 5.1 Two Tiers

**Tier 1 — Reflex loop (every cycle, no LLM):** a rule-based tree picks the
next action from the posture-valid set, biased by the current mood set by the
director. This is also the fallback whenever Claude is unavailable — the robot
never freezes because an API call failed.

Baseline tree (before director bias):

```
if posture == SLEEPING:
    return energy > 0.55 ? WAKE_UP : IDLE_CALM   // stay asleep, recover
if energy < 0.15:
    return path toward SLEEP (LIE_DOWN → SLEEP)
if hunger > 0.8 and lastInteraction > 30s ago:
    return SEEK_ATTENTION (stand/sit first if needed)
if boredom > 0.7 and energy > 0.5:
    return BACKFLIP or SPIN or PLAY_BOW
if curiosity > 0.6 and energy > 0.4:
    return WALK_SLOW or LOOK_* variants
if energy < 0.35:
    return SIT_DOWN / IDLE_CALM (recover)
else:
    return IDLE_CALM / occasional LOOK_*
```

**Tier 2 — Director (Phase 2, Claude):** every `directorIntervalMs`
(default 45s), or immediately after a significant event (owner interaction,
posture re-sync, any dimension crossing 0.2/0.8), Claude receives the full
personality state, posture, recent action history and the valid action set,
and returns a **behavior plan**: a mood label plus per-action weights (or a
short suggested sequence) that biases the reflex tree until the next director
call. One Claude call steers ~18 reflex decisions.

Cost at defaults: ~80 calls/robot/hour on `claude-haiku-4-5` with a small
prompt — orders of magnitude cheaper than per-action calls, and Claude latency
no longer sits inside the action cycle.

### 5.2 Director Prompt Content

- Personality state (all six dimensions, including contentment) and posture.
- Values rendered as integers 0–100 in the prompt (single convention).
- Last N actions with outcomes, time since last owner interaction.
- Only posture-valid, safety-valid actions listed.

### 5.3 Structured Output (no text parsing)

The director uses the **Anthropic Java SDK's structured outputs** — the schema
is derived from a record and enforced at the API level; no free-text parsing,
no "respond with ONLY the action name":

```java
record DirectorPlan(Mood mood, List<WeightedAction> bias, String reasoning) {}
record WeightedAction(Action action, double weight) {}

StructuredMessageCreateParams<DirectorPlan> params = MessageCreateParams.builder()
    .model("claude-haiku-4-5")
    .maxTokens(1024L)
    .outputConfig(DirectorPlan.class)
    .addUserMessage(prompt)
    .build();
```

The `Action` enum in the schema makes out-of-catalog answers impossible.
`reasoning` feeds the `BehaviorDecision` audit trail. On API error/timeout the
reflex tree simply continues with the previous plan.

Config: `behavior.claude.model=claude-haiku-4-5`, `timeout 10s`,
`behavior.use-claude-director=true|false`.

---

## 6. PERSONALITY UPDATE RULES

### 6.1 Action Impacts (applied on completion)

| Action group | energy | happiness | boredom | curiosity | hunger | contentment |
|---|---|---|---|---|---|---|
| WALK_* | −0.05 | — | −0.15 | −0.05 | — | +0.03 |
| PLAY (BOW/BACKFLIP/SPIN) | −0.10 | +0.10 | −0.25 | — | — | +0.15 |
| LOOK_* | −0.01 | — | −0.05 | −0.08 | — | — |
| SIT_DOWN / sitting | +0.03 | — | +0.08 | — | — | −0.02 |
| LIE_DOWN | +0.05 | — | +0.05 | — | — | — |
| IDLE_CALM | +0.02 | — | +0.03 | — | — | — |
| **SLEEP** | **+0.40** | — | reset to ≤0.3 | −0.10 | — | +0.05 |
| WAKE_UP | — | +0.03 | — | +0.05 | — | — |
| SEEK_ATTENTION | −0.03 | −0.02 | — | — | −0.05 | −0.05 |

SLEEP now has an explicit, meaningful recovery effect — the v1.0 nap-loop
(sleep 5s, wake exhausted, sleep again) cannot occur.

### 6.2 Passive Per-Cycle Drift (one consistent model)

Energy is changed **only** by actions (§6.1) — there is no separate passive
energy decay *and* recovery fighting each other. Passive drift per cycle:

```
if lastInteraction > 30s ago: hunger += 0.01; happiness -= 0.005
boredom += 0.01                          // unless SLEEPING
curiosity += 0.005                       // unless SLEEPING; satisfied by exploring
energy += 0.05                           // only while SLEEPING (so it wakes)
contentment += (0.5 - contentment) * 0.02  // drift toward neutral
```

Exploration *satisfies* curiosity (negative deltas on WALK/LOOK) while
curiosity rebuilds passively — otherwise "explore because curious" plus
"exploring raises curiosity" is a positive feedback loop that pins curiosity
at 100% (observed in the first live run).

### 6.3 Clipping

All values clipped to [0.0, 1.0] after every update. Failed actions apply no
impact (posture unchanged) but count in the audit trail.

---

## 7. SENSORS & EXTERNAL EVENTS

### 7.1 Actual Hardware (base Bittle X V2)

Built in: **6-axis IMU** (accelerometer + gyroscope on the BiBoard/ESP32),
**back touch sensor**, **microphone** (voice module). There is **no** distance,
LiDAR or camera hardware on the base model — the v1.0
`obstacleDetected`/`distanceToNearestObject` contract is removed. Distance/IR
etc. are optional add-on modules and may return as an extension later.

### 7.2 Hardware-Sourced Events

| Event | Source | Effect |
|---|---|---|
| OwnerPetted | back touch sensor | happiness +0.15, hunger −0.10, lastInteraction=now |
| OwnerCalledOut | voice module | hunger −0.20, curiosity +0.10, lastInteraction=now |
| PickedUp / FellOver | IMU orientation | posture re-sync, contentment −0.10, curiosity +0.10 |
| LowBattery | adapter | forces recovery bias (LIE_DOWN/SLEEP path) |

### 7.3 API-Sourced Events

`POST /api/robots/{id}/behavior/event/{type}` allows the dashboard to inject
`OwnerPetted`, `OwnerCalledOut`, `OwnerPlayed` (happiness +0.20, energy −0.15,
boredom −0.30). Same handler as the hardware path.

---

## 8. API CONTRACTS

### 8.1 Orchestrator → Adapter (new, adapter work required)

**POST /api/robots/{robotId}/execute_action**

```json
// Request
{ "action": "walk_slow", "durationMs": 3000, "sequenceId": 42 }

// 200
{ "robotId": "bittle-1", "action": "walk_slow", "success": true,
  "actualDurationMs": 2987, "message": null }

// 400
{ "success": false, "message": "Action not supported", "action": "unknown" }
```

`sensorFeedback` is intentionally absent until real sensor plumbing exists;
touch/IMU events arrive via the event channel instead.

### 8.2 Orchestrator Behavior API (all under one prefix)

Base path: `/api/robots/{robotId}/behavior`

| Method | Path | Purpose |
|---|---|---|
| GET | `/personality` | current PersonalityState (incl. posture) |
| GET | `/status` | loop running?, current/last action, decision source |
| GET | `/history?limit=50` | recent BehaviorDecision audit entries |
| POST | `/start` / `/stop` | control the autonomous loop |
| POST | `/event/{type}` | inject an owner/sensor event |
| POST | `/action/{action}` | enqueue a manual action (coordinated, §4.3) |

(The v1.0 doc's bare `/api/robots/{id}/personality` is gone — that path
belongs to the deprecated adapter proxy.)

### 8.3 Dashboard Integration

Behavior events ride the **existing STOMP layer**: after every decision/action
cycle the loop publishes to `/topic/robot/{robotId}/behavior` (decision,
personality snapshot, posture). No new polling endpoint; `FleetBroadcaster`'s
legacy adapter-personality broadcast is retired with the adapter migration
(§2.3). "Next action prediction" is dropped from the contract.

---

## 9. DATA MODEL (Java, package `com.bittle.orchestrator.domain.behavior`)

- `Posture` — enum.
- `Action` — enum carrying id, duration, `EnumSet<Posture> validFrom`,
  resulting posture, `PersonalityDelta` impact, min-energy safety gate.
- `PersonalityDelta` — record of six deltas, `applyTo(state)`.
- `PersonalityState` — mutable per-robot state + posture + metadata; `clip()`;
  `snapshot()` record for JSON/STOMP.
- `PersonalityStateManager` — applies action impacts, passive drift, events.
- `DecisionEngine` — interface; `RuleBasedDecisionEngine` (Phase 1),
  `ClaudeDirector` (Phase 2).
- `BehaviorDecision` — record: robotId, timestamp, state snapshot, valid
  actions, chosen action, source (RULE/CLAUDE/MANUAL), reasoning, result.
- `ActionExecutor` — adapter call + error mapping (`application.service`).
- `RobotBehaviorLoop` / `BehaviorLoops` — per-robot loop and its registry
  (`application.service`).
- `application.usecase` — one class per operation the API exposes
  (`StartBehaviorLoopUseCase`, `ApplyBehaviorEventUseCase`, `SubmitManualActionUseCase`,
  ...); see `docs/design/ARCHITECTURE.md`.

Persistence (Phase 4): `BehaviorDecisionEntity` via existing Postgres/JPA;
personality snapshot saved on loop stop and restored on start.
`behavior.persist=true|false`.

---

## 10. ROADMAP

**Phase 1 — Core infrastructure (orchestrator, this phase):**
domain model incl. posture, PersonalityStateManager, rule-based DecisionEngine,
ActionExecutor + `PythonServiceClient.executeAction`, per-robot behavior loop,
REST API, STOMP events, config, unit tests. Runs fully without Claude.

**Phase 1b — Adapter execution endpoint (Python):**
`POST /execute_action` mapping the action catalog to Petoi skills; disable
adapter autonomous mode when orchestrator loop is active.

**Phase 2 — Claude director:** Anthropic Java SDK dependency, DirectorPlan
structured output, prompt builder, event-triggered director calls, feature
flag + fallback behavior already in place.

**Phase 3 — Hardware events:** touch/IMU event channel adapter→orchestrator,
posture re-sync, voice events.

**Phase 4 — Persistence & dashboard:** decision audit trail in Postgres,
personality persistence, GUI panels on the STOMP topics.

**Phase 5 — Tuning:** real-robot testing, delta balancing, adapter legacy
endpoint removal (migration step 3).

---

## 11. CONFIGURATION

```properties
behavior.decision-interval-ms=2500      # pause between autonomous actions
behavior.sleep-decision-interval-ms=5000
behavior.history-size=200
behavior.auto-start=false               # loops started via API by default

# Phase 2
behavior.use-claude-director=false
behavior.director-interval-ms=45000
behavior.claude.model=claude-haiku-4-5
behavior.claude.timeout-ms=10000
```

---

## 12. TESTING

- Unit: state manager update/clip/drift rules, decision tree per posture and
  per state extreme, action posture filtering, SLEEP/WAKE cycle (no nap loop).
- Integration: loop against a mocked adapter; manual-vs-autonomous queue
  coordination; STOMP event emission.
- Phase 2: director plan schema round-trip, fallback on timeout.
- Real robot: action mapping, duration calibration, safety gates.
