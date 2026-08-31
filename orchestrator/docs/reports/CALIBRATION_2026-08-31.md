# Dead-Reckoning Calibration Session — 2026-08-31

**Setup:** 1×1m grid on a thick textured gym mat (terrain proxy), Bittle X on battery,
adapter over WiFi WS. Interactive protocol: operator measured/reset between runs.
**Session ended:** battery depleted mid-ladder (charging); remaining items listed in §5.

## 1. Test 1 — Linear accuracy: PASS

| Cycles (`kwkF n`) | Distance | Per cycle |
|---|---|---|
| 1 | 0.100m | 0.100m |
| 3 | 0.340m | 0.113m |
| 6 | 0.675m | 0.1125m |

**Calibration:** `STRIDE_PER_CYCLE = 0.112m` (gym mat), first cycle ≈ 0.10m
(start-up transient). Model: `distance = 0.10 + 0.112 × (n−1)`; residual error <2%.
The doc's assumed 0.42m/cycle was 3.7× off.

**Flag:** systematic rightward heading drift ~2.5–3°/cycle — lateral displacement grows
quadratically (2cm @ 3 cycles → 11cm @ 6). Straight walks trace an arc; needs IMU
heading correction en route (§4). Walking itself tracks straight; the abrupt
end-of-gait lay-down animation adds a per-stop displacement.

## 2. Test 2 — Turning: closed-loop turns are good; measurement is the hard part

Tape-measure + clock-position estimates proved too coarse (±15°), and one unattended
6-turn sweep was invalidated (§3). The supervised per-turn IMU ladder
(yaw via `gp` before/after each turn, operator re-centering between runs) gave:

| Commanded | Measured (IMU) | Verdict |
|---|---|---|
| L 30 | 16.0° | suspect (early run; re-test pending) |
| R 30 | 30.4° | exact |
| L 65 | 65.7° | exact |
| R 65 | 58.7° | −10% |
| L 90 | 92.6° | exact (operator confirmed visually) |
| R 90 | 27.3° | clipped — see below |

**Shallow-turn hypothesis (leading):** the closed-loop turn grinds until the gyro target
is reached; on the soft mat progress can be slow, the harness's fixed ~10s wait then
aborted still-running turns via the `kup` re-arm. Battery-voltage sag late in the session
(pack hit empty shortly after) compounds it: weak servos → slower rotation → more
clipping. Harness now polls yaw during the turn and waits for settle; re-run pending.

**Turn geometry (validated across tape-measured trials):**
- Turns are ARCS, never pivots: radius ~0.33m at 90° (chords 55–57cm, L/R mirror-symmetric),
  shallower (~0.5m+) at small angles. A 180° arc displaces the body exactly 2R laterally.
- `kwkL 180` sits on the firmware's unwrapped-yaw ±180 edge case — under-rotated ~15°.
  Avoid; compose 180s from two 90s.
- Yaw sign convention: left = positive delta, right = negative; the raw yaw domain
  extends beyond ±180 (observed −106..+287) — normalize deltas mod 360.

## 3. Operational facts learned (hard-won; encode in any driver)

1. **Consecutive bounded gaits are silently dropped** — interleave `kup` between them
   (and tolerate `kup` reporting failure when already standing).
2. **WS completion echo for `kwk*` is immediate**, not at motion end — wall-clock
   waits or yaw-settle polling required. (`gp`/`g*` are gait-safe to poll mid-motion.)
3. **Fall-recovery contaminates everything.** The mat edge is a drop; going over
   triggers the firmware's automatic self-righting flips (cannot be disabled in stock
   firmware short of `gu`, which kills balance + yaw too). Three runs were invalidated
   this way, including the entire unattended 6-turn sweep. Bound cumulative arc
   displacement to the arena (60cm+ margin per 90° turn) or supervise per-run.
4. **The stand-up transition itself can stumble the dog off an edge.**
5. **Stand/lie transitions rotate the body 12–25°** — bracket measurements tightly
   around the motion, not around posture changes.
6. **Battery voltage is a calibration variable.** Stamp every measurement with the `P`
   voltage readout; expect stride/turn performance to sag with the pack.

## 4. Improvement plan — gait, walking, path prediction, sensors

### Software only (no hardware, highest leverage)
- **Feedback-corrected turning:** turn → read `gp` → issue corrective turn until within
  tolerance. Immune to surface/battery variance; each `gp` costs ~0.2s. This replaces
  open-loop turn calibration entirely.
- **Mid-walk heading hold:** poll `gp` during straight walks (gait-safe) and cancel the
  ~3°/cycle rightward drift with small corrective turns at leg boundaries.
- **Voltage-aware execution:** read battery before each leg; refuse/flag precision moves
  below a threshold; optionally scale predicted stride by voltage (calibratable).
- **Path model:** poses evolve by arcs (R(angle) lookup) + strides (first-cycle 0.10,
  then 0.112/cycle) + per-stop lay-down offset; waypoint graph over metric grid.
- **Servo trim:** the rightward walk bias suggests a small calibration offset (`c` command)
  could straighten the gait at the source — worth one supervised tuning session.

### Custom firmware (cheap to build — Arduino IDE, vendored libs)
- **Configurable fall-recovery:** replace auto-flip with freeze-and-report (host decides).
  The reaction is one block in `reaction.h`.
- **Deferred gait completion over WS** so `completed` = motion end (the newer source tree
  already has `deferSkillTokenEcho`).
- **Wrapped-yaw fix / clean yaw endpoint**, removing the ±180 edge case and the odd domain.

### Sensor integration (from the firmware capability catalog)
- **RGB ultrasonic (`XU`, Grove):** forward range → obstacle stop, wall-following,
  arena-edge detection (would have prevented every contaminated run). Pushes readings
  over WS (`event_us`). Cheapest, highest value first add-on.
- **Servo feedback reads (`fp`)** if the installed servos support it: true joint angles →
  stall/obstruction detection — the "stuck detector" the spatial MVP lacks.
- **Back-touch pad (`XB`):** free petting/interaction events for the personality system.
- **Camera (`XC`, Mu3/Grove Vision AI V2):** landmarks/visual odometry — BUT enabling it
  disables the IMU in stock firmware (hard conflict with everything above; needs the
  custom-firmware route or a host-side camera instead).
- **The scalable path: a Pi Zero riding the dog** on the Grove UART (a 4th full command
  port, default-enabled) carrying its own camera/ToF/IMU — proper sensor fusion without
  fighting the BiBoard's constraints.

## 5. Remaining test items
- Re-run L30 and R90 with the settle-polling harness at known battery level.
- Optional: verify turn-radius lookup at 45°; `kvtL/R` (turn-in-place gait) evaluation
  on the mat — if it works, it may beat arcs for tight-space mapping.
- Test 3 (combined L-path) with feedback-corrected turns — validates the full
  dead-reckoning loop end to end.
