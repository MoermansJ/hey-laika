# Planning Brief — Request Metrics & the "Mind" Tab

**Date:** 2026-09-01 · **Status:** planning input
**Goal:** two observability features for the GUI: (A) a fleet-level **Metrics**
page tracking every request the system makes, and (B) a per-robot **Mind** tab
showing Laika's ongoing reasoning — where it thinks it is, its map of the
environment, what it's doing and why.

**Relationship to other briefs:** the Mind tab is mostly *integration* — nearly
all of its panels are streams other briefs already define (behavior status,
senses layer, map layers, leash zones). Metrics is self-contained. Both are
GUI + thin service work; no firmware involvement.

---

## A. Request metrics

### A.1 What to measure (per robot + fleet rollup)

| Layer | Metrics |
|---|---|
| **Robot WS channel** (the scarce resource) | commands sent; send→`completed` latency (the adapter already awaits completion echoes — latency is one subtraction); error/timeout counts by kind; heartbeat RTT; reconnects; connection uptime %; sniff count (senses layer) |
| **Adapter HTTP** | request count + latency per endpoint; 4xx/5xx |
| **Orchestrator** | proxied request counts; `502 adapter_unavailable` count (adapter health at a glance) |
| **AI calls** (the money) | Claude decision-engine calls, tokens in/out, estimated cost; Ollama calls + latency |
| **Behavior framework** | behaviors executed by source/priority; preemptions; `busy` rejections — the arbiter is one choke point, so these are one counter each |

### A.2 Implementation (lean)

- **Orchestrator:** Spring Boot Actuator + Micrometer — HTTP metrics are nearly
  free; custom counters for proxy/AI. (Micrometer also makes a Prometheus
  endpoint a later zero-cost option; do NOT build Grafana-anything now.)
- **Adapter:** Flask before/after-request hooks for HTTP; the controller's
  existing command path timestamps for WS metrics; counters exposed on a
  `/metrics` snapshot endpoint, merged by the orchestrator.
- **Storage:** in-memory rolling windows (last 1 h fine-grained, 24 h coarse);
  optional later: hourly rollup rows in Postgres for history. No time-series DB.
- **FE:** `metrics.html` + nav.js destination (fleet-level page, like settings/
  debug): fleet overview cards (requests/min, error rate, AI cost today, robot
  uptime), per-robot table, small SVG sparklines, recent-errors feed. Plain
  polling every few seconds — metrics don't need STOMP.

## B. The Mind tab — Laika's ongoing reasoning

Per-robot tab alongside Control / Voice / Behavior. Principle: **honest
provenance, not fabricated inner monologue** — every panel shows real system
state and real causality. Panels and their sources:

| Panel | Content | Source (brief) |
|---|---|---|
| **Where am I** | perceived room + confidence, pose marker with uncertainty blob that grows between sniffs and snaps on scan | senses layer `location.changed` + odometry shadow (nav §3) |
| **My map** | the perceptual map with layer toggles (trail/free-space, per-AP heatmaps, emergent-room clusters, sonar occupancy) — the same renderer as the map GUI, embedded | nav §2 |
| **What I'm doing** | current behavior, step m/n, source + priority, queue | `/topic/robot/{id}/behavior` (framework brief — exists) |
| **Why** | causality feed: `event → binding → behavior` lines ("battery.level 25% → binding 'tired' → tired_animation \[lifecycle]") | activity log enriched with binding provenance — requires events/executions to carry a `cause` reference; small framework addition, flag for the planner |
| **Senses ticker** | last sniff (age, BSSID count), ultrasonic distance, voltage, yaw; leash zone + RSSI when in away mode | event_us / cached `P` / `gp` / leash STOMP topic |
| **Agent thoughts** | when the Claude director / decision engine acts: the decision and its rationale text verbatim | behavior/decision services (framework Phase 4) |

- **Transport:** reuse existing per-robot STOMP topics; one new
  `/topic/robot/{id}/mind` only if consolidation proves cleaner than
  subscribing to several.
- **Ships incrementally:** a v0 is buildable *today* from what exists (current
  behavior, activity log, voltage); the location and map panels light up as the
  nav brief's phases land. Design the tab as a grid of independent panels each
  tolerant of "no data yet" so it never blocks on another brief's progress.
- **Optional garnish (explicitly later):** a playful one-line "thought bubble"
  generated from real state via Ollama (personality tie-in). Cosmetic only —
  must be visually distinct from the provenance panels so play never
  masquerades as truth.

## C. Phasing

- **M1 — Metrics core:** adapter hooks + `/metrics` snapshot; orchestrator
  Micrometer + merge endpoint; `metrics.html` with cards + per-robot table.
- **M2 — Metrics depth:** AI token/cost counters, behavior-framework counters,
  sparklines, recent-errors feed.
- **N1 — Mind v0:** tab scaffold (independent panels, no-data tolerant): What
  I'm doing + Why (needs the `cause` provenance addition) + Senses ticker.
- **N2 — Mind spatial:** Where-am-I and embedded map panels as nav Phases B–C
  deliver; Agent-thoughts panel with framework Phase 4.

## D. Open questions → RESOLVED (owner decisions, 2026-09-01)

1. **Retention: Postgres rollups, kept permanently.** No pruning — hourly rows
   are ~9k/year/robot; size is a non-issue. In-memory windows remain only as
   the serving cache for the live page.
2. **AI engine: default the decision engine to local Ollama** (zero cost,
   offline-capable); Claude becomes an *optional* engine for heavyweight
   director-level reasoning if/when wanted. `DECISION_ENGINE` is already
   pluggable (a `mock` exists) — add `ollama`. Metrics track call counts and
   latency for both engines; token/cost accounting activates only while the
   Claude engine is selected (adapter-measured via the SDK `usage` block,
   SQLite-persisted counters, orchestrator-priced — as previously leaned).
   Latency note: LLM decisions are occasional director-level choices; the
   2.5 s reflex cycle stays rule-based, so local-inference latency (seconds)
   is acceptable.
3. **Provenance: confirmed, and it captures BOTH the raw and the processed
   trigger.** The chain is: raw event (type + payload snapshot) → matched
   binding (id + filter + priority *as configured at fire time*) → arbiter
   submission → execution record (+ `preemptedBy`). Raw alone can't explain
   which behavior ran (the binding decides that); the binding alone can't show
   what data fired it. Manual = `{type: manual}`; agent =
   `{type: agent, decisionId}`. Build now, before Phase 3 expands the event
   surface.
4. **Fleet scope: fleet of 1 — design for Laika only.** Keep the existing
   `/api/robots/{id}/` routing (established pattern, not worth fighting), but
   stop designing for a hypothetical robot #2: no capability registry, no
   genericity requirements beyond the no-data tolerance panels need anyway.

**References:** `docs/design/NAVIGATION_MAPPING_BRIEF.md` (§2 map layers, §3
senses layer), `docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md` (STOMP behavior topic,
activity log, arbiter as single choke point),
`docs/design/PROXIMITY_LEASH_BRIEF.md` (leash STOMP/zones), GUI assets:
`static/nav.js`, per-robot tab pattern (`voice.html`, `behavior.html`),
`vendor/stomp.umd.min.js`.
