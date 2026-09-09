# Navigation Phase 1 — occupancy map, click-to-go, reactive stop, error dialogue

**Date:** 2026-09-09 · **Status:** built and tested against the simulated room;
live checks on the dog listed in §8 are still open.
**Input:** the "Bittle AI Companion: Autonomous Navigation & SLAM Design" plan
(ten tickets). This document records what was built, where the plan was bent
to fit the hardware and the existing code, and what remains for the floor.

## 1. What the plan assumed, and what is true

| Plan | Reality on Laika | What was built |
|---|---|---|
| Sensors at 50–100 Hz | Every read is one locked WebSocket round trip (50–90 ms); the ranger is ~10 Hz at best, the IMU yaw shares the same lock, the firmware's IMU stream is capped at 5 Hz | A 6 Hz sensor loop (`NAV_SENSOR_HZ`) that runs while she has moved in the last 3 s; yaw read at every gait boundary |
| IMU on the XIAO | The ICM42670 is on the BiBoard; the XIAO has mic, camera, LED | Yaw via `gp` on the dog's transport |
| Step counting, accelerometer dead reckoning | No step counter; accel integration is a dead end (spatial review) | Bounded gait cycles × the calibrated stride model, corrected by the IMU yaw after every burst |
| Occupancy grid and A* in Java, `/map/current` in Flask | The orchestrator has no control loop, only 4–10 s broadcast schedulers; pose and senses live in the adapter | Everything at sensor rate in the adapter (Python); the orchestrator relays and serves the Map tab |
| JSON map on a Pi | No Pi; the adapter runs in Docker on the PC with SQLite | Table `map_cells` in `bittle.db` |
| Strafe to avoid | No sideways gait | Stop, step back one cycle, replan |
| A separate avoidance loop | The arbiter is the single owner of motion | Avoidance submits `obstacle_stop` at safety priority; overrides are behaviors that carry a suppress-avoidance flag |
| Flask serves the GUI | The console is orchestrator-served static pages | The Map tab grew an occupancy layer, click-to-navigate, navigation, error and sensor cards |

## 2. Layers as built (adapter, `dog/app/`)

**Layer 1 — reactive stop** (`navigator.py`, the sensor loop). Reads the
ranger through `RangerService` (throttled, battery-saver gated) and records
every tick in `sensor_log.py`. A fresh reading at or under `stopCm` (25)
while the last motion command was a forward gait or a turn submits the seeded
`obstacle_stop` behavior (`kup`, `kbkF 1`, `kup`) at priority 1, integrates
the echo into the grid, raises `nav.blocked`, and marks a running route as
blocked. The stop is skipped while `arbiter.avoidance_suppressed()` is true.

**Layer 2 — map** (`occupancy.py`, `map_builder.py`). 10 cm cells, log-odds
per cell (+0.85 per echo, −0.4 per cell the beam crossed, clamped ±4). A cell
reads *occupied* at ≥ 1.5 (two net echoes), *free* at ≤ −0.4. Human
corrections pin a cell at ±3. The builder reports contradictions before it
writes: an echo inside a cell that is confidently free (≤ −1.2), or a beam
crossing a cell that is confidently occupied (≥ 1.7). No echo is not treated
as free space (the validation notes trace misses to the target). Readings
under 4 cm are dropped as the dog's own body.

**Odometry** (`senses.py`). Stride model from the 2026-08-31 calibration:
0.10 m for the first cycle, 0.112 m per cycle after. `fuse_yaw()` reads `gp`
and replaces the dead-reckoned heading; the first fuse after a restart
adopts the current heading as the reference (yaw counts from boot, the map
from the last origin reset), `reset_pose()` re-anchors both. Uncertainty
(`driftM`) grows by 15 % of commanded travel plus 1 cm per move.

**Layer 3 — routes** (`path_planner.py`, `navigator.py`). A* over the grid,
8-connected, no corner cutting, occupied cells and a one-cell halo blocked,
unknown cells allowed at 1.6× cost. Line-of-sight pruning keeps a detour over
seen floor instead of cutting back through the unexplored. A route is a
generator-backed arbiter behavior (`navigate`): sonar sweep at the start,
then per leg a closed-loop turn (`kwkL/R deg`) when the bearing differs by
more than 12°, and forward bursts of at most 3 cycles (`kwkF n`) capped by the
free distance ahead. After every command the yaw is fused, a look-ahead
reading is integrated, and the leg is recomputed from the corrected pose. A
blocked burst re-plans from where she stands; more than 8 re-plans or 5 stops
end the route as *unreachable*. Arrival is within 15 cm.

**Layer 4 — errors** (`nav_errors.py`). `RecoverableError` kinds:
`map_contradiction`, `sensor_anomaly` (a jump over 100 cm while still, or 12
missed echoes in a row while moving), `localization_drift` (IMU disagrees
with dead reckoning by more than 30°), `action_failed` (a command was not
accepted). The handler waits 300 ms and counts per kind; a clean re-check
clears the streak (silent recovery); the third strike escalates.
`UnrecoverableError` (`lost` at 3 m of uncertainty, or an escalation) enters
the error state: arbiter stop, `error_halt` at safety priority, mood light
held on a red 2 Hz blink, the prompt spoken through the speaker, `nav.error`
raised, navigation refused with 409 until a human answers `trust_sensor`
(pin the cells the reading saw), `trust_map` (pin what the map believed) or
`manual` (forget the route; reset the origin from the Map tab if she was
moved). Every occurrence and answer lands in `nav_errors`.

**Sweeps.** `sonar_sweep` pans the head (joint 0, `m 0 deg`) through
−90..90° in 30° steps, reads at each, and integrates all seven rays from the
standing pose. Needs the ranger on the head (`NAV_RANGER_ON_HEAD`, default
on); set it false if the ranger is mounted on the body and the sweep and the
start-of-route scan are skipped.

**Data for later** (`sensor_log.py`). `sensor_readings`: one row per loop
tick. `action_log`: one row per motion command with the snapshot at send
time and an outcome. Export as JSON or CSV.

The generator extension to the arbiter (`submit_generator`, `on_end`,
`suppress_avoidance`) is the framework extension the navigation brief §5.3
predicted; a stored behavior may also be submitted with the flag.

## 3. Adapter API (all under `/api/robots/bittle-1`)

| Route | Method | What |
|---|---|---|
| `/sensors/latest` | GET | Newest loop reading; `?fresh=1` reads now |
| `/sensors/recent` | GET | Ring buffer newest first (`?limit=`, `?since=`), `?stored=1` from SQLite, `?format=csv` |
| `/navigation` | GET | State, target, route, avoidance, sensor loop, map counts, error summary, config, stats |
| `/navigation/config` | POST | `stopCm`, `sensorHz`, `avoidanceEnabled`, `sweepAngles`, `maxCyclesPerBurst`, … |
| `/navigation/target` | POST | `{x, y}` metres in the map frame; 409 in the error state or away mode |
| `/navigation/cancel` | POST | Stop the route |
| `/navigation/map` | GET | Cells `[cx, cy, f\|o, logodds]`, bounds, counts, pose, target, route |
| `/navigation/map/reset` | POST | Clear the grid |
| `/navigation/map/cell` | POST | `{cx, cy, state}` human correction |
| `/navigation/sweep` | POST | Head-pan scan (arbiter behavior) |
| `/navigation/override` | POST | `{behavior}` or `{command, settleS}` with avoidance stood down |
| `/navigation/errors` | GET | Active error, streaks, history (`?limit=`) |
| `/navigation/errors/respond` | POST | `{choice: trust_map\|trust_sensor\|manual, note}` |
| `/navigation/data/export` | GET | `?kind=actions\|readings`, `?format=csv\|json`, `?since=`, `?limit=` |

The orchestrator relays every route at the same path and the export as a
binary relay so the CSV content type survives.

**Events** raised through the framework (bindable, and mapped to the mood
light): `nav.blocked {obstacleCm, x, y}` (amber flash), `nav.arrived {x, y}`
(green flash), `nav.unreachable {reason}`, `nav.error {kind, message,
errorId}`, `nav.error.resolved {kind, choice, errorId}`, `map.updated
{version}`.

**Configuration** (`dog/.env.example`, passed through compose):
`NAV_ENABLED`, `NAV_STOP_CM`, `NAV_SENSOR_HZ`, `NAV_GRID_RES_M`,
`NAV_RANGER_ON_HEAD`, `NAV_SPEAK`, `NAV_ALWAYS_SAMPLE`.

## 4. Frame and units

x east, y north, metres, from the origin set by `POST /senses/pose/reset`
(the dog's home spot), heading in degrees counter-clockwise from +x. Cell
index = floor(coordinate / 0.10). The Map tab draws y upward.

## 5. Data glossary (for the ML work)

`action_log` rows: `t` epoch seconds when the command was sent; `command` the
firmware token; `kind` advance / turn / skill / joint; `gait` the gait name
(`wkF`, `bkF`, `wkL`, …); `source` the arbiter behavior running (`navigate`,
`obstacle_stop`, `sonar_sweep`, `override`, a stored behavior, or `direct`
for the console); `x, y, heading` the dead-reckoned pose at send time; `yaw`
the last fused IMU yaw; `rangeCm` the last loop reading; `battery` percent;
`targetM` the planned advance (null unless known); `outcome` `sent`, later
`failed`, `blocked`, `arrived` (filled by the navigator); `endedAt`.

`sensor_readings` rows: `t`; `rangeCm` (null = no echo or gated); `rangeOk`;
`x, y, heading, driftM` pose; `yaw`; `battery`; `command` in flight;
`behavior` running; `panDeg` head pan when the reading was taken.

`nav_errors` rows: `t`, `kind`, `tier`, `retries` (strike number for
recoverable rows, streak length for the escalation), `message`, `context`
(the cells, reading and pose involved), `resolution`, `note`, `resolvedAt`.

## 6. The simulated room

`dog/app/mock_world.py` gives the mock controller a 4 × 3 m room with a
30 cm box 1.2 m ahead of the start. Bounded gaits move the dog by the same
stride model the senses layer assumes, the ranger ray-casts the walls, `gp`
reports the true heading. `MOCK_RICH` adds ±1.5 cm of echo noise. The tests
in `dog/tests/test_navigator.py` drive routes, the stop, overrides and the
error dialogue against it, and a Mocha instance on port 15002 lets the Map
tab be exercised without the dog.

## 7. Known limits

- Forward-only sensing while walking: obstacles beside her are seen only by
  sweeps, so a route that hugs a wall can clip it. The one-cell halo helps.
- The ranger's beam is wide (the 2026-09-03 notes): "nearest thing ahead",
  not a point. Thin table legs may be missed; low objects below the beam are
  invisible. Floor only, no cliff detection.
- The map is metrically fuzzy: yaw fusion holds the heading, but position
  still drifts with stride variation between surfaces. A route longer than a
  few metres deserves a sweep at the far end before it is trusted.
- Voice answers to the error prompt are not wired; the three choices are
  buttons on the Map tab (and the REST route). The conversation tool can be
  taught them later.
- Camera frames are not logged (disk budget); Phase 2 visual odometry will
  need its own capped store.

## 8. Live checks still open (need the dog on the floor)

The runbook. Greeting off (`POST /greeting/disable`), leash off, battery
above the saver's eco threshold, floor clear, a tape measure, and the Map tab
open on Mocha's neighbour Laika. Record results as an addendum here.

1. **Ranger placement.** Confirm whether the ranger is on the head (pans
   with joint 0) or the body. Set `NAV_RANGER_ON_HEAD` accordingly. If on the
   head, run `POST /navigation/sweep` from the tab and check that the seven
   readings match the room (walls at the measured distances). If the beam
   catches her own snout at some pan angles, drop those angles from
   `sweepAngles`.
2. **Stride on this floor.** Put her at a mark, `Reset origin`, run
   `POST /arbiter/invoke` with a stored behavior of `kwkF 6`, measure. If the
   distance differs from 0.10 + 5 × 0.112 = 0.66 m by more than 5 %, set
   `strideMPerCycle` for this floor (senses config) and the planner's
   `strideMPerCycle` to match; carpet has its own gait and needs its own
   number.
3. **Reactive stop.** Ranger on, avoidance on, `stopCm` 25. Hold a box 60 cm
   ahead, invoke `kwkF 6` from the Control tab. Expected: she stops within one
   cycle of the box at ~25 cm, backs one cycle, the tab shows a reactive stop
   and the box appears as obstacle cells. Then the same with a person's leg
   (soft target: expect misses, check she still stops).
4. **Override.** Box at 20 cm, `Override` with `kjmp`. Expected: she jumps,
   no stop fires during the jump (the stop counter does not move), and a
   `kwkF 1` afterwards toward the box does trigger it.
5. **Walk a square.** Click-to-navigate to four corners of a 1 m square in
   turn. Expected: arrival within 15 cm each time, the trail on the map is a
   square, the room's walls show as obstacle bands where the sweeps saw them.
   Note the yaw corrections in the sensors card; a correction over 30° means
   the turn constants need the gait learner again.
6. **Detour.** Box on the direct line to a target 2 m away. Expected: the
   start sweep maps the box, the route bends around it, arrival. Then the box
   placed *after* the sweep: a reactive stop, a re-plan, arrival.
7. **Error dialogue.** With the box mapped, remove it and navigate through
   its cells three times (three contradictions of one kind). Expected: the
   red blink, the spoken prompt, `nav.error` in the activity log, targets
   refused with 409, then "Map is right" from the tab releases the light and
   the cells; "Sensor is right" after re-placing the box pins them.
8. **Ten minutes of use.** Roam by clicking targets for ten minutes. Then
   `GET /navigation/data/export?format=csv` and `?kind=readings&format=csv`;
   check rows are continuous (no gaps longer than a second while moving),
   every action has an outcome, and the loop rate in the sensors card stayed
   near 6 Hz while walking.
9. **Sniffer interplay.** Confirm the WiFi sniff never fires during a route
   (the senses card's last-sniff age keeps growing while she walks) and
   resumes within a minute of arrival.

What cannot be done without the dog is exactly this list; everything above
§8 runs in CI against the simulated room.
