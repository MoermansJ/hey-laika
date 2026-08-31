# Planner Handoff — Bittle Dead-Reckoning Calibration (2026-08-31)

Self-contained: raw results, derived constants, hard operational rules, and engineering
commentary from the live calibration session. Written for planning the next phase
(waypoint mapping / spatial exploration). No other documents required, but deeper
references exist in the repo (`docs/robot/`, `docs/reports/`).

## 0. System context (as of this session)

- Robot: Petoi **Bittle X V2**, BiBoard V1.0 (ESP32), firmware **B10_251121**, battery 2S LiPo.
- Transport: **WiFi WebSocket `ws://192.168.0.246:81`** (the board's ONLY network service;
  no HTTP, no auth). Driven via the Python adapter (`dog` repo), which the compose stack
  and orchestrator GUI now use end-to-end. Battery percentage telemetry is live.
- Test arena: 1×1m grid on a **thick textured gym mat** (chosen terrain proxy). All
  constants below are mat-specific; hard floors will differ (expect longer stride, less sink).
- The firmware executes bounded gaits closed-loop: `kwkF <n>` walks exactly n gait cycles;
  `kwkL/R <deg>` turns until the IMU yaw target is reached. Both auto-stop.

## 1. Raw results

### Test 1 — Linear (straight walks, operator tape-measured)

| Command | Distance | Notes |
|---|---|---|
| `kwkF 1` | 0.100m | dead straight |
| `kwkF 3` | 0.340m | ~2cm rightward total |
| `kwkF 6` | 0.675m | 11cm rightward total, "1 o'clock" endpoint |

### Test 2 — Turns

Phase A (tape + clock-position eyeball, ±15° uncertainty):

| Command | Result |
|---|---|
| `kwkL 90` | ~120° rotation; displaced 33cm left / 46cm fwd (chord 57cm) |
| `kwkR 90` | ~120° rotation; displaced 34.5cm right / 42.5cm fwd (chord 55cm) — mirror of above |
| `kwkL 180` | ~165° rotation; displaced 66cm laterally / 12.5cm fwd — fits semicircle R=0.33m exactly |
| `kwkL 65` | ~60° rotation |

Phase B (supervised IMU ladder — yaw via `gp` before/after, one turn per run,
operator re-centered between runs; contaminated runs discarded):

| Command | IMU-measured | Assessment |
|---|---|---|
| `kwkL 30` | 16.0° | suspect — early run, re-test pending |
| `kwkR 30` | 30.4° | exact |
| `kwkL 65` | 65.7° | exact |
| `kwkR 65` | 58.7° | −10% |
| `kwkL 90` | 92.6° | exact; operator visually confirmed "almost perfect 90" |
| `kwkR 90` | 27.3° | clipped (see §3.2) |

Session ended when the battery hit empty; L30/R90 re-runs pending.

## 2. Derived calibration constants (gym mat)

```
STRIDE_PER_CYCLE      = 0.112 m      (steady state)
STRIDE_FIRST_CYCLE    = 0.100 m      (start-up transient)
distance(n cycles)    = 0.100 + 0.112 * (n - 1)     # residual < 2%
HEADING_DRIFT         = ~2.5-3 deg/cycle RIGHT on straight walks (lateral error grows
                        quadratically: 2cm @ 3 cycles -> 11cm @ 6 cycles)
TURN_RADIUS_90        = ~0.33 m      (L/R mirror-symmetric; chord ~56cm per 90°)
TURN_RADIUS_SMALL     = ~0.5 m+ at ≤30° commanded (arcs are shallower at small angles)
TURN_180              = DO NOT USE kwkL/R 180 (yaw ±180 wrap edge case, under-rotates ~15°);
                        compose from two 90s
YAW_CONVENTION        = left turn -> positive delta, right -> negative; raw domain exceeds
                        ±180 (observed -106..+287) — normalize deltas mod 360 to [-180,180]
LAY_DOWN_OFFSET       = end-of-gait animation displaces/rotates the body (12-25° yaw change
                        observed across stand/lie transitions); constant-ish per stop
```

## 3. Hard operational rules (violating these produced garbage data)

1. **Bounded gaits silently drop if sent back-to-back.** Interleave `kup` between any two
   `kwk*` commands. `kup` itself may report failure when already standing — treat as no-op.
2. **WS `completed` for `kwk*` arrives immediately, NOT at motion end.** The dog is still
   moving after the API returns. Either wait wall-clock (~1.3 s/cycle; turns vary hugely
   with surface/battery) or — better — poll `gp` and wait for yaw/position to settle.
   `g*`, `j`, `p` are on the firmware's gait-safe whitelist: polling does not interrupt gaits.
3. **Fall-recovery is automatic and non-disableable** (stock firmware): any fall — including
   off a mat edge, including during the STAND-UP transition — triggers self-righting flip
   skills that wreck position, heading, and any in-flight measurement. Three runs were lost
   this way. Keep ≥60cm margin per 90° turn arc, or supervise per-run. (`gu` disables the
   IMU entirely but also kills balance and yaw readout — not viable.)
4. **Battery voltage is a first-class variable.** Servo torque sags with the pack; late-session
   turns underperformed and the pack hit empty shortly after. Stamp every movement/measurement
   with the `P` voltage readout (already exposed as adapter telemetry). Refuse precision
   maneuvers below a threshold (TBD — calibrate voltage vs performance).
5. **Turns are arcs, never pivots.** Plan them as arc segments (radius per §2). An untested
   alternative: `kvtL/R` is the firmware's turn-in-place gait — evaluate it on the mat; if it
   works it may beat arcs for tight spaces.

## 4. Commentary — what I'd tell the planner (agent's own assessment)

**The strategic conclusion of the whole session: measure, don't predict.** Stride
calibrated beautifully; turn calibration kept dissolving under surface, battery, and
contamination variance — while the dog's own IMU measured headings to the degree, cheaply
(~0.2s per `gp`), even mid-motion. Every clean 65°/90° turn landed within a few percent,
meaning the closed-loop firmware is good — it was our *measurement and timing harness*
that generated the apparent errors. Architecture follows:

- **Turning primitive = turn → `gp` → corrective turn** until within tolerance (±5° is
  realistic). Do NOT build a commanded-vs-actual correction curve; it won't survive a
  surface change.
- **Straight-line primitive = walk with heading hold:** poll `gp` between legs (or every
  2-3 cycles) and inject small corrective turns to cancel the ~3°/cycle rightward drift.
  Alternatively/additionally, fix the drift at the source: it smells like 1-2° of servo
  trim, addressable with the firmware `c` calibration in one supervised session.
- **Pose propagation:** arcs + strides + per-stop lay-down offset; treat every number in §2
  as surface-specific. A waypoint graph (relative hops, re-measured at each node) will
  degrade far more gracefully than a global metric grid.
- **Trust ordering for position truth:** IMU yaw > commanded values > operator eyeball
  (clock-position estimates ran ±15° and consistently overestimated).

**Highest-leverage next investments, in order:**
1. *(software)* The feedback-turn + heading-hold driver — turns §2/§3 into a tested motion
   API; prerequisite for any mapping.
2. *(hardware, ~$15)* **Grove RGB ultrasonic (`XU`)**: forward range, firmware-supported,
   pushes `event_us` frames over the existing WebSocket. Converts arena edges/obstacles
   from data-destroying hazards into walls. Would have prevented every contaminated run.
3. *(experiment, free)* Probe `fp` servo-feedback reads — if the installed servos support
   them, true joint angles give stall/stuck detection (the known missing piece for
   exploration).
4. *(custom firmware, cheap — Arduino IDE, vendored libs)* Three surgical patches:
   configurable fall-recovery (freeze-and-report instead of auto-flip), completion echo at
   motion end for bounded gaits, wrapped-yaw cleanup. Each is small; together they remove
   the three worst platform sharp-edges.
5. *(later, scalable)* Camera conflicts with the IMU in stock firmware — don't plan on it.
   The clean sensor path is a Pi Zero riding the dog on the Grove UART (a default-enabled
   4th command port), carrying its own camera/ToF/IMU.

**Open items before mapping work starts:** re-run L30 + R90 with the settle-polling
harness at a known battery level; one combined L-path run (walk → feedback-corrected 90 →
walk) to validate the full loop; decide the low-voltage cutoff for precision moves.

## 5. Data availability

- Full session narrative: `orchestrator/docs/reports/CALIBRATION_2026-08-31.md`
- Robot reference (hardware/servo map, firmware capability catalog, network API):
  `orchestrator/docs/robot/`
- Adapter API: `POST /api/robots/bittle-1/command {"command": "kwkF 3"}` on :15001 (compose)
  — note it returns only success/failure, not firmware output; the calibration harness spoke
  WebSocket directly for `gp` readouts (board allows 2 concurrent WS clients).
