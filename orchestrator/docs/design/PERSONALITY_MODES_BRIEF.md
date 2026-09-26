# Planning Brief — Personality modes: Stationary Assistant, Roaming Assistant, Fruitfly

**Date:** 2026-09-19 · **Status:** planning input
**Builds on:** `BEHAVIOR_FRAMEWORK_BRIEF.md` (the arbiter, stored behaviors,
priority ladder), `NAVIGATION_MAPPING_BRIEF.md` (occupancy grid, navigator,
senses layer), `STATIONARY_SENSING_BRIEF.md` (look-around scans, the
sit-vs-stand camera-angle answer), `CONVERSATION_BRIEF.md` (wake → listen →
think → speak). Written after a codebase pass to ground this in what has
actually shipped, not just what those briefs proposed.

## 0. The ask

A new **Personality** page, three cards, each a whole-robot operating mode:

1. **Stationary Assistant** — sits, stays put, watches from one spot, exists
   mainly to talk.
2. **Roaming Assistant** — walks the apartment autonomously, builds a map,
   and drops **collection points**: a photo plus a description of what's in
   it, pinned to the map.
3. **Fruitfly** — driven by a live simulation of the MaleCNS connectome
   (Google Research / HHMI Janelia, released 2026-09-03: 166,700 neurons,
   25.6M synapses, the whole adult male CNS) instead of by the owner. No
   chat, no manual control while it runs — something else is driving.

## 1. Naming: this is not the six-dimension "personality"

`domain.behavior.PersonalityState` already means something specific: energy,
happiness, boredom, curiosity, hunger, contentment, ticked by
`RuleBasedDecisionEngine` every cycle (`ARCHITECTURE.md` §3–4). The three
cards are a different axis — *which systems are allowed to move her and
why* — not a mood. Calling both "personality" in code would collide two
real concepts under one name.

Decision: the GUI page is titled **Personality** (matches the ask) and shows
three mode cards; the code calls the new concept **mode**
(`OperatingMode`: `STATIONARY`, `ROAMING`, `FRUITFLY`). The existing
`PersonalityState` keeps its name and keeps running underneath Stationary
Assistant mode (§4) unchanged. Docs and code use "mode" throughout; only the
page title says "Personality."

## 2. A gap this surfaced: the orchestrator loop isn't an arbiter client yet

`BEHAVIOR_FRAMEWORK_BRIEF.md` §5 phase 4 ("personality loop migrates from
direct `execute_action` to arbiter client") is still open. Checked directly:
`RuleBasedDecisionEngine.decide()` never actually selects `WALK_SLOW`/
`WALK_FAST` on its own — its whole decision tree is postural/in-place
(sit/stand/look-around/play-in-place/sleep), so this isn't a "she might walk
off mid-conversation" risk. The real hazard is narrower but still real:
`dog/app/app.py`'s `/execute_action` route (what `ActionExecutor` calls)
sends straight to `bittle_controller` and only checks the adapter's own
*deprecated* autonomous loop — it has no idea the `Arbiter`
(`dog/app/arbiter.py`) exists. So a `SIT_DOWN` from the orchestrator loop
and a walking burst the arbiter is mid-way through for Roaming or Fruitfly
can land on the single motion WebSocket at the same time. This brief does
not attempt the full arbiter migration (that is its own project); it works
around the gap with a blunt but correct rule (§6): **the orchestrator's
behavior loop only runs during Stationary Assistant mode** — started when
that mode is entered, stopped before Roaming or Fruitfly take the arbiter.
No action-set filtering needed; stop/start is enough.

## 3. Shared plumbing

### 3.1 Source of truth

`OperatingMode` is orchestrator state (Postgres, like `personality_states`
and `leases`): a `robot_mode` table, one row per robot
(`robotId, mode, changedAt, changedBy`), behind a new
`RobotModeRepositoryPort` / `RobotModeRepositoryAdapter`, same shape as
`PersonalityStateRepositoryPort`. Default on first boot: `STATIONARY` — the
safest baseline (no autonomous walking, always answers if spoken to).

New use case `SetRobotModeUseCase(robotId, mode)`:

1. Reject if the target mode's prerequisites aren't met (e.g. `FRUITFLY`
   with the brain process unreachable — §5.5) with a typed exception mapped
   to a 4xx, same pattern as `BehaviorLoopHeldElsewhereException`.
2. Stop the behavior loop if it's running and the target isn't `STATIONARY`.
3. Start the behavior loop if the target is `STATIONARY` and it isn't
   already running.
4. Relay a `POST /mode {mode}` to the adapter through `RobotAdapterPort`'s
   untyped relay (`ARCHITECTURE.md` §5) — the adapter is the one that
   actually flips conversation/navigation/fruitfly on and off.
5. Persist, then broadcast on a new `/topic/robot/<id>/mode` STOMP topic
   (same pattern as `/behavior`).

`FleetInitializer` re-pushes the last known mode to the adapter on
orchestrator restart, same reasoning as the lease re-acquire path.

### 3.2 Adapter side (`dog/app/mode.py`, new)

A small service next to `leash.py`/`mood.py` in shape. `set_mode(mode)`:

| Leaving → | Conversation/ears | Navigation autonomy | Eyes | Fruitfly brain |
|---|---|---|---|---|
| `STATIONARY` | stop listening | — | — | — |
| `ROAMING` | — | stop explore, cancel route | — | — |
| `FRUITFLY` | — | — | — | stop the sim, release the arbiter |

| Entering → | Conversation/ears | Navigation autonomy | Eyes | Fruitfly brain | Posture |
|---|---|---|---|---|---|
| `STATIONARY` | start listening (existing `conversation.py` wake path) | disabled (manual click-to-navigate on the Map tab still works if the owner wants it) | on | — | `idle_sit` once |
| `ROAMING` | stays available — a wake word still preempts exploration (arbiter: manual/safety > agent) | start the explore generator (§5) | on | — | stand (`kup`) before the first scan |
| `FRUITFLY` | stopped | disabled | off (nothing consumes it in v1) | start | whatever the sim's first command leaves her in |

Firing `set_mode` also emits a `mode.changed {mode}` event through the
existing `EventBinder`, so a binding can react (e.g. the mood light
described in §5.7 of `NAVIGATION_MAPPING_BRIEF.md`'s addendum could turn an
eerie purple in Fruitfly) — a nice-to-have, not required for v1.

### 3.3 GUI

New `personality.html`, added to `TABS` in `app.js` (`app.js:275-287`
pattern) — but this one probably doesn't belong as a per-robot *tab*
alongside Control/Behavior/Map; given fleet-of-one and that mode is a
whole-robot state the owner sets once and leaves, it reads better as the
**default landing view** for the robot page (or a prominent card pinned
above the tab strip) rather than a tab you have to remember to click. Lean:
add it as a tab named "Personality" for v1 (cheapest, consistent with every
other page), revisit promoting it to the landing view once it exists and
that friction is felt for real.

Three cards, each: name, one-line description, the current-mode highlight,
a "select" action. Selecting a card calls `POST /api/robots/{id}/mode` and
re-renders. Below the cards, the active mode's own status strip:

- **Stationary:** a shortcut into the Mind tab's arbiter-thoughts feed
  (`mind.html`) filtered to non-locomotive actions, plus the conversation
  state badge already built for the Audio input tab.
- **Roaming:** exploration state (idle / walking / scanning / low battery /
  no frontier left), stops-so-far count, a link to Map with the new
  collection-points layer on.
- **Fruitfly:** sim tick rate, uptime, last three decoded commands, and the
  **Exit Fruitfly mode** button (§5.6 — the one interaction the mode allows).

## 4. Stationary Assistant

Nothing new to build here beyond the mode plumbing (§3) — it composes two
systems that already exist and already agree with each other:

- The orchestrator behavior loop, for the in-place idle/personality ticking
  (posture, looking around, play-in-place, sleep) — already exclusively
  in-place per §2, so nothing new is needed to keep her from wandering off.
- The conversation state machine (`dog/app/conversation.py`), for the
  verbal-assistant purpose the mode exists for.

Both already default to a sitting posture on the paths that matter (idle
ladder's `idle_sit`, conversation's wake-triggered `idle_sit`), which lines
up with `STATIONARY_SENSING_BRIEF.md`'s answered open question 4: sitting
pitches the head ~45° up, wrong for room scans but fine — even good — for
looking at a standing conversation partner's face. No separate "camera
angle for talking" decision needed; the existing sit behavior already
produces the right angle for this mode's actual job.

One small addition: the orchestrator's rule engine already runs
`LOOK_AROUND_LOW` (sitting) as part of the idle cycle — worth leaving as is
rather than adding new vision behavior; Eyes/YOLO person-detection already
runs during this mode (§3.2) and can inform "is anyone in front of me"
without a new subsystem.

## 5. Roaming Assistant

The heaviest *legitimately new* work of the three, but it stands on real,
shipped ground: `dog/app/navigator.py`, `occupancy.py`, `map_builder.py`,
`senses.py` (WiFi fingerprints, pose), and the arbiter's `sonar_sweep`/
`goto`-style bounded-burst pattern. `explore_and_map` itself — the frontier
picker — does not exist in code yet; neither do landmarks or scan bundles
from `STATIONARY_SENSING_BRIEF.md`. This brief ships a **lighter v1** of
that sensing brief's §4 vantage planner, not the full pipeline (YOLO
landmarks, monocular depth, place signatures deferred — §5.8).

### 5.1 The explore loop (new generator behavior, `dog/app/explorer.py`)

A generator behavior, same shape as the navigator's route execution
(`Arbiter.submit_generator`, already exists per the mapping brief's
2026-09-09 addendum):

1. Candidate vantage points = free cells on the frontier of the occupancy
   grid (free next to unknown) — reuse `occupancy.py`'s grid directly, no
   new map representation.
2. Score = unknown cells a look from there would newly see (ray-cast on the
   current grid), v1 simplification: no energy-per-metre division
   (`STATIONARY_SENSING_BRIEF.md` §4's full score) — just walk to the
   nearest high-score candidate. The energy-aware scoring is a real
   improvement but needs calibration data this project doesn't have yet;
   revisit once a few sessions' worth of battery-drain-per-action data
   exists in the log (the sensing brief's own dependency).
3. Walk there via the existing navigator (A*, bounded bursts, reactive
   obstacle stop already live).
4. On arrival: stand (if not already), take one photo, caption it (§5.2),
   store a collection point (§5.3).
5. Repeat. Stop when: no frontier cell scores above a threshold, or battery
   drops below the configured floor (reuse `power_saver.py`'s tiers), or a
   session cap (distance or wall-clock, configurable, default something
   modest like 20 minutes) is hit. Any of these just leaves her standing —
   no need for a special "done" posture.
6. Any higher-priority arbiter submission (a fall, an obstacle stop, a wake
   word, a manual command) preempts at the next bounded-gait boundary,
   exactly like the navigator does today; the generator resumes or
   re-scores on return, same as a route recovers from a block.

Away mode (`leash.py`) already gates `explore_and_map`/`goto_room` off per
the mapping brief §5.5 — reuse that gate verbatim; Roaming mode simply never
starts the explorer while away.

### 5.2 Captioning (new, local, per `prefer-local-ollama`)

One photo per vantage point, captioned by a **local vision-capable Ollama
model** — reuse `voice.py`'s Ollama HTTP client pattern
(`query_ollama`), extended to pass an `images` field (Ollama's
`/api/generate` already accepts base64 images for vision models; no new
transport). Start with `moondream` (1.6B, built for captioning, cheap
enough on CPU to run once per vantage point without slowing the walk) —
measure quality once on a real room, same "measure once, then choose"
approach the conversation brief used for its LLM size; step up to
`llava:7b` if `moondream`'s captions are too thin. New env var
`OLLAMA_VISION_MODEL` alongside the existing `OLLAMA_MODEL`. Prompt: ask for
one or two plain sentences naming what's visible, no markdown — same
length discipline the conversation brief applied to spoken replies, because
these captions render as map tooltip text.

### 5.3 Collection points (new table + API + Map tab layer)

New adapter table `collection_points`: `id, t, x, y, heading, photoPath,
caption, battery`. Frames saved to disk the same way the sensing brief
proposed for scan bundles (`dog/data/collection_points/<id>.jpg`, a size-
capped ring — reuse that idea even though the full scan-bundle system
isn't being built yet).

API: `GET /api/robots/<id>/collection_points` (same filter shape as
`GET /senses/samples`: `since`/`until`/`limit`), `GET
/collection_points/<id>/photo` (binary relay, same pattern as
`RelayGetBinaryFromRobotUseCase`/`getBinary` already does for
`/eyes/snap`). No orchestrator release needed for the JSON route (untyped
relay); the binary route needs one new typed relay use case, mirroring the
existing `/eyes/snap` one.

Map tab (`map.html`): a fifth layer checkbox, "collection points," next to
occupancy/route/trail/grid (`map.html:97-104`). Points render as a distinct
marker (a small photo-frame icon, not a plain dot, so they read differently
from WiFi samples at a glance). Hover shows a thumbnail + first line of the
caption (same `tip` element the WiFi samples already use); click pins the
full photo + caption + pose into the existing "Selected sample" detail
card's pattern (`renderDetail`, `map.html:466-488`) — this is close to a
copy-paste of code that already exists, not new design.

### 5.4 Posture and camera angle, applied

Directly answers the part of the ask about sitting-vs-standing angles:
every capture happens standing, per the sensing brief's answered question —
sitting's ~45°-up pitch sees ceiling, not the room. No new finding needed
here; this just wires the existing answer into where the photo gets taken.

### 5.5 Stopping/interaction

A wake word or manual command during Roaming preempts the explorer exactly
as the arbiter's priority ladder already guarantees (manual/safety >
agent); it doesn't need to be modeled as a mode change. Only an explicit
mode switch (Stationary or Fruitfly) turns exploration off for good.

## 6. Fruitfly

The riskiest, longest-lead piece, and the one the owner explicitly wants
built as the real thing rather than a nod to it. Grounded against what's
already public, sixteen days after the connectome's release
(2026-09-03 → today):

- **Data:** `male-cns:v1.0` on neuPrint. Free account, an API token (same
  shape as `ANTHROPIC_API_KEY` — new `.env` entry `NEUPRINT_TOKEN`),
  `neuprint-python` for the client. [Janelia's male-cns download
  page](https://male-cns.janelia.org/download/) and [the male-cns project
  page](https://www.janelia.org/project-team/flyem/male-cns-connectome) are
  the canonical sources; `neuprint-python`'s
  [query docs](https://connectome-neuprint.github.io/neuprint-python/docs/queries.html)
  cover pulling the neuron/synapse tables and per-neuron cell-type/
  predicted-neurotransmitter metadata needed to sign the connectivity
  matrix (excitatory/inhibitory) and to find named cell types for §6.2.
- **Prior art, all from this same two-week window, worth studying before
  writing a line of sim code:**
  [`cobanov/awesome-fly`](https://github.com/cobanov/awesome-fly) and
  [`townie/awesome-fruit-fly`](https://github.com/townie/awesome-fruit-fly)
  are curated lists of the connectome-to-robot/game projects that appeared
  since release — the fastest way to find a working sensorimotor bridge
  instead of designing one from a blank page.
  [`psmorph/male-cns-fly-brain`](https://github.com/psmorph/male-cns-fly-brain)
  is a leaky-integrate-and-fire sim over the same dataset (built for escape
  behavior, not locomotion, but the loading/simulation scaffolding
  transfers). Dorian Todd's [Fly Brain Bridge](https://www.doriantodd.com/projects/fly-brain-bridge/)
  wires MaleCNS to a walking robot (Sesame) by stimulating identified
  input neurons and reading whatever command neurons the fly's own wiring
  decides on — the closest published analog to what this brief proposes.
  [`Frankweb33/flybrain-robot-bridge`](https://github.com/Frankweb33/flybrain-robot-bridge)
  closes the loop with optical flow and IMU feedback over UDP, which is the
  natural v2 once Laika's own ranger/camera should feed the sim instead of
  running it open-loop.

### 6.1 Simulation

`dog/fruitfly/` — a **separate process**, not inside the `dog` Flask
container: `neuprint-python`, a sparse-matrix/LIF stack (numpy/scipy to
start; Arbor if performance demands it — several of the prior-art projects
above use Arbor for exactly this scale) don't belong in the same image that
owns the robot's realtime WebSocket, and a slow/misbehaving sim must never
be able to stall motion control. It talks to the `dog` adapter over plain
HTTP on the same host (localhost), the same trust boundary as Ollama today.

1. Build the weight matrix once (cached to disk — 166,700 × 166,700 sparse,
   ~25.6M nonzeros is a large but entirely tractable sparse structure) from
   neuPrint's synapse table, signed by predicted neurotransmitter.
2. Tick a leaky-rate or LIF update (`activity[t+1] = decay·activity[t] +
   f(W · activity[t] + drive[t] + noise)`) at a modest rate (tens of Hz is
   plenty; Laika's own command cadence is much slower than that).
3. v1 drive is open-loop — tonic/noise input into sensory neuropils, no
   camera/ranger grounding — matching how the original write-up reads
   ("I read neural activity from it, translate that into high-level
   commands"), not a closed loop. Closing the loop with Laika's ranger and
   camera (matching `flybrain-robot-bridge`'s approach above) is a named v2,
   not required for the mode to exist.

### 6.2 Motor readout

Identify descending-neuron populations by cell type via neuPrint's
metadata and published locomotor-control literature (the giant-fiber/
moonwalker-descending-neuron family the search above surfaced is exactly
this kind of cell type — forward/turn/backward command neurons are a
studied area, not a guess this brief has to make cold). Read the relevant
populations' activity each tick, threshold with hysteresis (avoid
chattering between commands faster than Laika can execute a bounded burst),
emit one of `FORWARD / LEFT / RIGHT / STOP`.

### 6.3 Bridge into the arbiter

A new generator behavior, `dog/app/fruitfly_drive.py`, structurally the
navigator's bounded-burst pattern again: poll the sim's current decoded
command, submit one short gait burst (`kwkF`/turn-in-place) at `agent`
priority, yield, repeat. The arbiter's safety tier (fall recovery,
low-battery rest, obstacle stop) still sits above `agent`, so physical
safety rails are never bypassed even though the *owner* has none.

### 6.4 What "no interaction" cannot honestly mean

Taken completely literally, zero interaction removes any way to recover a
stuck or unwanted-behaving robot short of killing a process by hand. That's
a real hazard, not a purity concern. Deviation, stated plainly: the GUI
keeps one button, **Exit Fruitfly mode**. It does not steer her — it only
switches the mode (§3), which stops the sim and hands the arbiter back.
That is the single interaction the mode allows, and it's an off-switch, not
a joystick, so it doesn't compromise the "something alien is driving" idea
the mode is going for.

### 6.5 GUI, no chat box by design

The Fruitfly card, once selected, renders only: sim status (tick rate,
uptime), the last few decoded commands, a live strip chart of the readout
populations' firing rate (a genuinely fun thing to watch — `dataviz` skill
guidance applies if this gets built as more than a debug view), and the
Exit button. No text input, no manual servo controls rendered anywhere on
the page while this mode is active — reinforcing the concept is a GUI
decision, not just a backend one.

### 6.6 Kill criterion

If the sensory drive can't be coaxed into producing a legible forward-vs-
turn signal in early bench testing (sim running, commands logged, no robot
attached yet), the fallback is the lighter "reactive wander" design that
was the alternative option for this mode — small, reuses shipped
navigation/obstacle-avoidance code, ships in days not weeks. Decide this
after the bench spike (§7, phase F-1), not before.

## 7. Phasing

- **P1 — Mode plumbing (orchestrator + adapter + GUI shell).** `robot_mode`
  table/port/use case, `dog/app/mode.py`, the mode STOMP topic,
  `personality.html` with three cards and mode switching, the loop-gating
  rule from §2. No new sensing/AI yet — this alone makes Stationary
  Assistant real (§4 needs nothing else).
- **P2 — Roaming v1.** `explorer.py` frontier picker (no energy scoring),
  `collection_points` table + relay routes, Map tab layer. Vision
  captioning stubbed to a fixed string first, then wired to Ollama once the
  walk-and-photograph loop is proven on its own.
- **P3 — Roaming captioning.** `OLLAMA_VISION_MODEL`, the caption prompt,
  quality check against `moondream` vs `llava` on real rooms.
- **F1 — Fruitfly bench spike.** Connectome download + weight-matrix build
  + sim loop running headless, logging decoded commands against synthetic
  drive, no robot attached. This is where the kill criterion (§6.6) gets
  evaluated.
- **F2 — Fruitfly on the robot.** `fruitfly_drive.py`, the arbiter bridge,
  the GUI card, live test with a spotter present (new, untested motion
  source — treat the first live run like a firmware flash: supervised,
  battery watched, e-stop hand on the Exit button).
- **E — Refinements (either roaming or fruitfly, as they prove out):**
  energy-aware vantage scoring once action-log drain data exists; closed-
  loop sensory drive for Fruitfly; landmarks/depth from
  `STATIONARY_SENSING_BRIEF.md` if collection points want richer content
  than one photo + caption later.

## 7a. P1 status and the concrete P2/F1 plan (2026-09-19)

P1 shipped: `robot_modes` table, `SetRobotModeUseCase`/`GetRobotModeUseCase`/
`ResyncRobotModesUseCase`, `ModeController`, `dog/app/mode.py`, the
Personality tab. All tests green (92 orchestrator, 311 adapter). Roaming and
Fruitfly currently do nothing beyond stopping conversation/eyes — §5/§6
below are unbuilt. Machine this will run on, checked directly: 12 logical
cores, 16 GB RAM, an AMD Radeon RX 5700 XT (no CUDA — ROCm on Windows is not
worth fighting for this). That rules a GPU path out for Fruitfly's sim and
argues for plain CPU sparse math, not Arbor's GPU backend.

**P2 — Roaming v1, concrete file plan:**

- `dog/app/explorer.py` (new): `ExplorerService`. Frontier cells = free
  cells adjacent to unknown ones in `nav_grid` (`OccupancyGrid`, already
  live). Score = nearby-unknown-cell count ÷ `nav_planner`'s path distance
  to it (no energy calibration yet, per §5.1). Walks there via the
  navigator's existing target mechanics (the same path `/navigation/target`
  already drives), submitted as a generator behavior like `sonar_sweep`. On
  arrival: stand, one photo, caption (stubbed to a fixed string until P3),
  one `collection_points` row. Repeats until no frontier scores above a
  threshold, battery floor, or a session cap.
- `dog/app/models.py`: `CollectionPoint` (id, t, x, y, heading, photo_path,
  caption, battery).
- Routes: `GET /collection_points`, `GET /collection_points/<id>/photo`.
- Orchestrator: one new typed binary relay use case (mirrors
  `RelayGetBinaryFromRobotUseCase`/`/eyes/snap`) for the photo; the list
  route needs no orchestrator release (untyped relay).
- `map.html`: a fifth "collection points" layer, reusing the existing
  hover/pin/detail pattern.
- `dog/app/mode.py`: `_apply("roaming")` currently does nothing beyond
  enabling conversation/eyes — this phase wires `ExplorerService.start()`/
  `stop()` in.
- Nothing here needs Laika connected to write and unit-test (mock
  controller, same as P1); a real walk is needed to tune the session-cap
  defaults (open question 1) and is the first thing that does need her on.

**F1 — Fruitfly bench spike, concrete file plan:**

- Needs `NEUPRINT_TOKEN` in `dog/.env` — a free neuPrint account, human
  action, can't be done on the owner's behalf (§8 below).
- `dog/fruitfly/` (new, separate from `dog/app` — its own small
  `requirements.txt`: `neuprint-python`, `scipy`, `numpy`, `pyarrow`; kept
  out of the adapter's Docker image per §6.1's reasoning).
- `download.py`: pulls the three minimal-subset feather files (§6, ~1.15 GB)
  via `neuprint-python`, caches under `dog/fruitfly/data/`.
- `build_matrix.py`: `scipy.sparse.csr_matrix` from the connectivity table,
  signed by predicted neurotransmitter, cached to `.npz` so this only runs
  once.
- `sim.py`: the leaky-rate tick loop, headless, logging decoded
  FORWARD/LEFT/RIGHT/STOP to console/CSV — no robot, no arbiter yet. This
  is where the kill criterion (§6.6) gets checked: does the readout look
  legible, or is it noise?
- CPU-only (scipy sparse mat-vec on 25.6M nonzeros is milliseconds on this
  CPU) — no GPU work needed, sidestepping the AMD/no-CUDA situation
  entirely.

## 7b. F1 bench spike, done (2026-09-20)

`dog/fruitfly/build_matrix.py` and `dog/fruitfly/sim.py` built and run
against the real downloaded connectome (`download.py`'s output was already
on disk). Checked directly, not assumed from the brief's own numbers:

- The brief's "166,700 neurons" is `status == "Traced"` in the annotations
  feather (165,122 rows) — the raw flat-connectome weights file actually
  spans ~1.8M bodies once orphans/fragments/glia are included, so `Traced`
  is the filter that matters. Restricting both edge endpoints to that set
  produces 25,563,197 edges — matches the brief's "25.6M synapses" almost to
  the digit, confirming this is the intended reading of `male-cns:v1.0`.
- Motor readout (§6.2) resolved to concrete cell types instead of staying an
  open question: `DNp09` (2 cells, L/R) for forward, `MDN` (4 cells) for
  backward, `DNa02` (2 cells, L/R) for steering (right-minus-left activity).
  All four/eight cells are present and `Traced` — no fallback needed.
- Matrix build (once, cached to `.npz`/`.feather`): ~47s. Sparse mat-vec on
  the resulting 165,122 x 165,122 / 25.6M-nonzero matrix: ~29ms, i.e. ~34 Hz
  ceiling on this machine's CPU — comfortably inside the brief's "tens of Hz
  is plenty" and confirms open question 3 in favor of plain scipy sparse
  (no Arbor, no GPU needed).
- Model is a leaky-rate (Wilson-Cowan-style) network rather than a spiking
  LIF — bounded to [0,1] by construction regardless of gain, simpler to get
  right for a bench spike; `sim.py`'s docstring has the full writeup.
  Calibration sweep (gain x bias against a fixed tonic+noise sensory drive):
  found a regime (gain=0.05, bias=2.0) where the whole network stays
  moderately active (not saturated) while the tiny readout populations
  behave like sharp, mostly-mutually-exclusive switches — clean STOP gaps
  between BACKWARD/FORWARD/LEFT/RIGHT episodes, not simultaneous saturation
  and not silence. **Kill criterion (§6.6): passed** — the readout is
  legible, not noise. F2 (the arbiter bridge, `fruitfly_drive.py`) is not
  built and `sim.py` talks to nothing — headless only, per this round's ask,
  logging decoded commands to console + CSV for inspection.
- `dog/fruitfly/data/` (the downloaded feathers + cached matrix, ~1.1 GB) is
  now gitignored — wasn't before, and wasn't caught until this pass.

## 8. Open questions

1. Session cap defaults for Roaming (distance/time/battery floor) — pick
   after watching one real exploration run, not in the abstract.
2. `moondream` vs a bigger vision model for captions — settle in P3 against
   real rooms, same pattern as the conversation brief's LLM sizing.
3. ~~LIF library choice~~ — settled by §7b: plain scipy sparse, ~34 Hz
   ceiling measured on this PC, no Arbor/GPU needed. (Also settled as a rate
   model, not a spiking LIF — see §7b and `sim.py`'s docstring.)
4. Does Fruitfly's sensory drive stay open-loop indefinitely, or is closing
   it with the ranger/camera (like `flybrain-robot-bridge`) worth doing
   once F2 is stable? Lean: revisit only if open-loop wandering looks
   aimless in practice.
5. Should `personality.html` stay a tab or become the robot page's landing
   view (§3.3)? Revisit once it exists and the friction is felt for real.
