# Planning Brief — Navigation & Perceptual Mapping

**Date:** 2026-09-01 · **Status:** planning input
**Goal:** the dog autonomously roams the apartment, mapping WiFi signal strengths
and sonar returns into a *visual map of the environment as it perceives it* —
then uses that map to execute "go to the kitchen" and "come to me" as ordinary
behaviors through the behavior framework.

**Sits between:** `docs/reports/SPATIAL_MVP_REVIEW.md` (motion + dead-reckoned
pose — the foundation below), `docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md` (the
execution substrate above), `docs/design/PROXIMITY_LEASH_BRIEF.md` (phone
anchoring, shared firmware shopping list).

---

## 1. Perception sources (all validated or one small firmware token away)

| Source | What it gives | Cost |
|---|---|---|
| **WiFi fingerprints** — `WiFi.scanNetworks()` over all visible 2.4 GHz BSSIDs (apartment building ⇒ typically 5–20 neighbors' APs at fixed unknown positions) | A per-location RSSI *vector*: room-level (~2–4 m) place recognition, absolute (no drift), works from cold start. Never connects to anything. | New firmware token (~30 lines; the spatial review established fork changes are cheap). Scan takes ~2 s and degrades the WS briefly ⇒ **stop-and-sniff only**, never mid-gait. |
| **Dead-reckoned pose** — `gp` yaw + bounded gaits × calibrated stride (spatial MVP, live-validated) | Continuous x/y estimate between sniffs. Topologically right, metrically fuzzy, drifts. | Already scoped/validated in the spatial MVP. |
| **Sonar head sweep** — head-pan servo (joint 0, ±90°) + one-shot ultrasonic read (`XU`, native firmware support; module ~€10–15, already recommended by the spatial review) | A 180° range scan from a standing pose — poor-man's lidar. Obstacle points ⇒ walls/furniture edges on the map. | Module purchase; sweep is just servo commands + reads, no firmware change. |
| Firmware `EXCEPTION:` lines (fall/knock/push) | Free trail annotations. | None. |

Known caveats, inherited and accepted: 2.4 GHz only (fewer BSSIDs than a phone
sees); fingerprints drift over weeks as neighbors swap routers (auto-refresh
stored fingerprints on confident matches); stride varies by surface (carpet
gait exists; per-surface stride calibration).

## 2. The map model — "the apartment as the dog perceives it"

Stored adapter-side (SQLite, per the spatial review's storage decision):

- **Samples:** `(x̂, ŷ, t, {bssid: rssi}, voltage, events)` collected at every sniff.
- **Free space:** the thickened trail — everywhere the dog has walked is floor.
- **Per-AP heatmaps:** IDW-interpolated color fields per BSSID — the apartment as
  overlapping radio auras (the most literally "perceived" layer).
- **Emergent rooms:** cluster samples by fingerprint similarity; the dog segments
  the apartment into perceptual regions *unsupervised*. The user names the
  clusters ("kitchen") in the GUI — this replaces any manual training walk.
- **Occupancy points:** sonar sweep returns projected along pose+bearing — the
  layer that makes the render read as a floor plan rather than a heat blot.
- **Room graph:** named clusters become nodes; edges hold **routes** (turn/advance
  sequences) either taught by driving once via the GUI or auto-extracted from
  roam trails that crossed between clusters.

**Drift control — RSSI loop closure:** two samples with near-identical
fingerprints taken at different times are almost certainly the same place ⇒ a
constraint that bends the dead-reckoned trail back onto itself (pose-graph
relaxation; crude version: snap the pose when a scan strongly matches an old
one). Turns unbounded drift into bounded fuzz; the map *converges* with roaming
instead of degrading.

**Rendering:** extends the spatial MVP's planned SVG map GUI — layer toggles
(trail / heatmap-per-AP / clusters / occupancy), live pose marker whose
uncertainty blob grows between sniffs and snaps tight at each scan, STOMP-fed.

**Expectation to set:** room-scale truthful, metrically fuzzy — "your apartment
drawn from memory", sharpening with every roam. A first full map is an evening
of strolling (~2 s per sniff), not a sprint.

## 3. The senses layer — mapping is an always-on sense, not a task

Design principle (owner-confirmed): WiFi mapping is part of Laika's
*navigational senses* — it runs constantly, regardless of what behavior is
executing or who commanded it. Perception is therefore **not arbitrated**: the
arbiter owns motion; senses only observe. Three always-on taps:

1. **Odometry shadow.** Because ALL motion flows through the arbiter, a passive
   tracker taps the command stream and dead-reckons the pose continuously —
   manual driving, agent behaviors, play: everything updates x̂/ŷ. Navigation
   never needs to *own* motion to know what motion happened; the arbiter is the
   one place the body's entire movement is visible.
2. **Opportunistic sniffer.** A scan needs ~2 s of radio quiescence, so
   "constantly" means *every motion gap*, not a fixed clock: fire whenever the
   robot has been stationary a few seconds with no command pending, under a
   politeness contract — never delay queued work, min interval ~30–60 s,
   suppressed below the battery floor and in away mode (hotspot-walk scans
   don't belong in the home map). Idle sits, behavior settle times, and arrival
   pauses all become free sampling windows; the map accretes as a side effect
   of living.
3. **Event ingestion.** Firmware `EXCEPTION:` lines, ultrasonic pushes, and
   cached voltage reads annotate samples for free.

Because every sniff is pose-labeled by the odometry shadow, *any* activity
contributes to the map — a week of ordinary use maps the places Laika actually
frequents. `location.changed` likewise becomes a continuously available sense
output (GUI: "Laika thinks it's in: kitchen"; context for the Claude director),
independent of any navigation task.

**`explore_and_map` is therefore demoted** from "the way mapping happens" to an
optional *coverage accelerator*: a curiosity behavior that deliberately walks
toward unvisited or stale regions (frontier policy over sample density).
Mapping happens anyway; exploration just speeds up the corners the dog doesn't
naturally visit. The spatial review's safety rails bound it: floor only (no
cliff detection), boundary polygon, ultrasonic collision avoidance once the
module arrives, voltage-gated.

One mechanical consequence for the adapter: the scan token blocks the firmware
~2 s, so the transaction lock treats a sniff like any command (longer timeout);
the sniffer's politeness rule is what guarantees a manual command never waits
behind one.

## 4. Navigation: "go to the kitchen", "come to me"

- **goto(room):** sniff → localize (k-NN over fingerprints) → shortest path over
  the room graph → replay each edge route → stop-and-sniff at each node to
  confirm + re-anchor → arrival = fingerprint match, never trusted odometry.
- **come_to_owner:** voice/GUI gives *intent only* (single mic, no direction).
  Locating the owner costs one of the leash brief's phone paths:
  BLE app `readRSSI()` ⇒ warmer/colder search over the room graph (terminate on
  near-threshold), or UWB (§6 of the leash brief) ⇒ distance + bearing, true
  beelining. Ship search-based first.

### Vision satellite (decided 2026-09-01, hardware ordered)

Camera vision comes from a **self-contained satellite**, NOT the BiBoard:
Grove Vision AI V2 (Himax WiseEye2 NPU, on-module YOLO) stacked on a XIAO
ESP32S3 Sense (plug-together, pre-soldered), powered by its own 1S LiPo
(XIAO has charge management), streaming detections to the adapter over its
OWN WiFi. Rationale: the firmware's camera path on the Grove I2C socket
**disables the IMU** (recorded at CAMERA-disable time in the .ino), and the
IMU carries closed-loop turns + odometry — never trade it. The satellite
adds zero firmware risk and zero load on the robot's WS.

- Person bounding-box x-offset ⇒ follow-me steering through the arbiter
  (the missing directional signal §4 lacked).
- XIAO's own OV2640 ⇒ occasional full-res stills for room recognition;
  its PDM mic is a backup audio-capture channel for the voice relay.
- ⚠ The bare V2 module ships WITHOUT a camera — the OV5647 sensor is a
  separate line item (or buy Seeed's V2+camera+XIAO kit).
- Integration work when it arrives: XIAO sketch (detections → HTTP/WS to
  adapter), adapter listener ⇒ `vision.person` events into bindings,
  follow-me generator behavior. ~2–3 sessions.

---

## 5. Behavior framework integration (the load-bearing section)

Navigation extends the framework along **all three of its first-class notions**
and adds two framework extensions it was going to need anyway. The arbiter
remains the single motion owner throughout — which *retires* the spatial
review's "roaming needs a third-owner 409-guard" concern: mapping and goto are
just arbiter clients now.

### 5.1 New step types (usable inside ANY stored behavior)

The framework brief already reserved `goto: {x,y}` as a future step type; this
brief delivers its real form plus siblings:

| Step | Semantics |
|---|---|
| `goto_room: {room}` | Full §4 navigation as one step; yields at every bounded-gait boundary (~1–2 s), so preemption granularity is naturally fine. |
| `follow_route: {route}` | Replay one stored edge route (no planning). |
| `scan_wifi: {}` | Stop-and-sniff; emits a sample + localization update. |
| `sonar_sweep: {}` | Head-pan range scan; emits occupancy points. |
| `come_to_owner: {}` | §4 search behavior (BLE/UWB-gated). |

So "bedtime" can be authored in the builder GUI as data:
`goto_room: bedroom` → `ksit` → `sound: yawn` → `krest`.

### 5.2 New events (bindable like any lifecycle event)

| Event | Payload | Example binding |
|---|---|---|
| `location.changed` | `{room, confidence}` | entered kitchen → sniff-around flourish |
| `nav.arrived` | `{room}` | → bark once (arrival announcement) |
| `nav.blocked` | `{obstacleCm}` | persistent obstruction → whine + abort event |
| `nav.lost` | `{lastRoom}` | localization confidence collapsed → stop, scan-in-place recovery behavior; if still lost → sit + bark for help |
| `map.updated` | `{coverage}` | GUI refresh only (no motion) |
| `voice.phrase` *(already in the framework's table)* | `{phrase}` | "come" → `come_to_owner`; "kitchen" → `goto_room: kitchen`. The Bittle X voice module supports ~10 trainable custom phrases emitting `XAc` codes — offline voice→nav with no cloud. |

### 5.3 Two framework extensions this forces (flagging for the planner)

1. **Parameterized behaviors/bindings.** Today a binding is
   `{event, filter, behaviorName, priority}`. Navigation needs event payload →
   step arguments (`voice.phrase "kitchen"` must reach `goto_room` as
   `room=kitchen`). Extension: behaviors declare params; bindings carry a payload
   → param mapping. Generally useful (battery level into warning behaviors, etc.).
2. **Generator behaviors.** `explore_and_map` cannot be a static step list — its
   steps are produced by the exploration policy at runtime. Extension: a behavior may be
   backed by a step *generator* (adapter code) instead of stored steps. The
   arbiter doesn't care where steps come from; it still owns execution,
   preemption at step boundaries, and status broadcasting. (`goto_room` inside a
   stored behavior is likewise generator-expanded at execution time.)

### 5.4 Priority placement

Using the framework ladder (safety > manual > agent > lifecycle > idle):

| Activity | Priority | Rationale |
|---|---|---|
| Voice/GUI "come" / "go to kitchen" | **manual** | Direct human intent — same rank as a human at the GUI. |
| Claude director invoking `goto_room` | **agent** | Unchanged from the framework brief. |
| Scheduled nav (bedtime walk to crate) | **lifecycle** | Ordinary lifecycle behavior that happens to contain a nav step. |
| `explore_and_map` (coverage accelerator only — see §3) | **idle+** (above the sit/lie ladder, below lifecycle) | *Idle-time curiosity:* when the idle ladder would sit the dog down, an optional binding sometimes walks toward unvisited/stale map regions instead. Opt-in and voltage-gated; anything preempts it. |

The senses layer itself has **no row in this table** — it owns no motion and
needs no priority. Sniffing rides motion gaps under §3's politeness contract,
and the odometry shadow is a pure observer of the arbiter's command stream.
| `nav.lost` / `nav.blocked` recovery | **lifecycle** (motion) | These aren't safety events — the dog is confused, not endangered. Safety tier stays reserved for falls/battery/leash-lost. |

Preemption works for free: every nav step yields at bounded-gait boundaries, so
a manual command or safety event interrupts a `goto_room` within ~1–2 s, and the
generator receives the abort and emits a clean `nav.*` terminal event.

### 5.5 Mode interplay with the leash

Navigation is a **home-mode** activity; the leash is **away-mode**. The
home/away mode concept (leash brief, open question 4 — now answered: yes, it's
needed) gates them: away mode suppresses `explore_and_map` and `goto_room`
(the room graph is meaningless on a walk), home mode disarms the leash zone
machine. This avoids any priority arm-wrestling between leash reactions and
navigation — they never run in the same mode.

---

## 6. Consolidated firmware shopping list (cross-brief)

| Change | For | Brief |
|---|---|---|
| `event_rssi` push frame (AP RSSI ~1 Hz) | away-mode leash | leash §2 |
| Multi-SSID credentials | home↔hotspot without re-provisioning | leash §2 |
| Dead-man rest on WS silence | away-mode safety floor | leash §2 |
| **WiFi scan token** (all-BSSID RSSI list on demand) | fingerprinting | **this brief** |
| *(opt.)* BLE TX power token | short BLE leash | leash §4 |

One fork, one flash session covers all five; validate per the usual runbook,
back up servo calibration offsets first (spatial review §4b).

## 7. Phasing

- **A — Perception spike:** scan token in firmware; log fingerprints from a few
  hand-placed positions; confirm room-level k-NN discrimination in *this*
  building. *Kill criterion:* adjacent rooms indistinguishable → lean harder on
  sonar/occupancy and taught routes; fingerprints demote to coarse anchors.
- **B — Senses layer + render:** odometry shadow on the arbiter's command
  stream; opportunistic sniffer with the politeness contract; samples table;
  map GUI with trail + heatmap + cluster layers. From this phase on, the map
  grows during ordinary use. (Order the ultrasonic module now.)
- **C — Rooms + routes:** cluster naming UI; route teaching (drive-through
  recording) and auto-extraction from trails; room graph storage.
- **D — goto + framework wiring:** `goto_room` generator; parameterized
  bindings; `nav.*`/`location.changed` events; voice phrase bindings; arrival/
  blocked/lost behaviors seeded.
- **E — Refinements:** loop closure, sonar sweeps into occupancy layer, the
  `explore_and_map` coverage accelerator, `come_to_owner` (BLE search first).

## 8. Open questions

1. Clustering algorithm + fingerprint distance metric (start: Euclidean on
   shared-BSSID dBm with a missing-AP penalty; k-NN, k≈5) — tune in Phase A.
2. Auto-extracted routes vs taught routes when both exist for an edge — prefer
   taught? Blend by success rate?
3. Localization confidence model — what threshold flips `nav.lost`, and does
   confidence feed `location.changed` consumers?
4. Does `explore_and_map` deserve its own arbiter rung ("curiosity") or is
   idle+ via binding priority sufficient? (Lean: binding priority; no new rung.)
5. Multi-floor / duplicate-fingerprint spaces — out of scope for an apartment;
   note for the fleet future.

**References:** `docs/reports/SPATIAL_MVP_REVIEW.md` (validated motion
primitives, roam loop, storage/GUI decisions, safety rails),
`docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md` (steps/events/arbiter, priority
ladder, reserved `goto` step type), `docs/design/PROXIMITY_LEASH_BRIEF.md`
(phone anchoring paths, home/away modes, firmware list),
`docs/robot/HARDWARE.md` (head-pan servo joint 0, Grove UART),
`docs/robot/FIRMWARE_CAPABILITIES.md` (`XU` ultrasonic read, voice `XAc` codes).
