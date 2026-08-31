# Review: Spatial Exploration & Trail Recording MVP — Preparation Findings

**Date:** 2026-08-31
**Prepared against:** full source mining of `PetoiCamp/OpenCatEsp32` (now cloned at `F:\projects\robot\opencat-esp32`, snapshot `B10_260820`) + our validated protocol facts for the robot's `B10_251121`.
**Verdict:** The feature is buildable, but the doc's two load-bearing assumptions — firmware-side IMU odometry and a firmware stuck detector — **do not exist in any OpenCat firmware, stock or otherwise**. The good news: stock firmware turns out to offer three primitives the doc doesn't know about (absolute yaw telemetry, closed-loop turn-by-angle, bounded walk-N-cycles) that enable a *simpler* MVP with **zero firmware changes**. Stuck detection is the one piece that genuinely has no clean MVP answer and should be re-scoped.

---

## 1. What the firmware actually provides (the real foundation)

Mined from source; items marked ⚠ are newer than our robot's firmware and must be verified live (§4).

| Primitive | Command | Detail |
|---|---|---|
| **Absolute heading (yaw)** | `gp` (once) / `gP` (stream) | Prints `ICM: ax ay az yaw pitch roll` — fixed-width floats, yaw in degrees, drift-compensated Madgwick, zero = boot orientation. Stream is rate-capped ≤5 Hz (⚠ cap may be absent on ours). **Polling `gp` does NOT interrupt a running gait** — `g*`, `j`, `i/m`, `p`, `.`/`,` are on the firmware's gait-safe whitelist. |
| **Turn by angle, closed-loop** ⚠ | `kwkL 90` / `kwkR 90` | Firmware turns until yaw reaches target, auto-stops with `kup`, prints `endTurn`; the `k` echo arrives at completion. This is a ready-made navigation primitive. |
| **Bounded advance** ⚠ | `kwkF 5` (gait cycles) / `kwkF 3000` (ms) | Auto-stops with `kup`; completion echo deferred to the actual end. One `wkF` cycle ≈ 1.3 s at default speed. |
| **Gait set** | `kwkF/L/R`, `ktrF/L/R` (trot), `kcrF/L/R` (crawl), `kbkF/L/R` (back), `kvtL/R` (turn in place), `kcarpetF/L/R` | No arc/curvature parameter exists — steering is discrete gait swaps. `kup`/`kbalance` is the clean stop; `p` is freeze. |
| **Event lines** | (spontaneous) | `EXCEPTION: Fall over / Knocked / ^ ForceAngle:…` printed when the IMU detects flip/knock/push — usable as free trail annotations. |
| **Servo battery/voltage** | `P` | `Voltage: 7.85 V` — worth adding to telemetry while we're here. |

Also confirmed: the unsolicited `XAd`/`XAc`/`X` chatter is the **voice module's UART echoed verbatim**; `Xa` (lowercase) closes the module persistently and silences it — `XAd` alone does not. Useful during trail recording to keep the stream clean (but it would disable "Hey Laika" hardware voice reactions; it's reversible with `XA`).

## 2. What does NOT exist — the doc's broken assumptions

1. **No odometry, anywhere.** No position estimate, no step counter exposed, no world-frame displacement. The doc's §3.2 firmware sketch (`Odometry odom`, `update_odometry`, `detect_step`) is *hypothetical code* — implementing it means a custom firmware fork. Also: accel double-integration is a dead end here — gait vibration dominates the signal and the printed accel is body-frame (world-frame is computed for the MPU6050 only and never printed).
2. **No stuck detection.** Verbatim from the source: `IMU_EXCEPTION_OFFDIRECTION` and `IMU_EXCEPTION_FREEFALL` are **dead code** (triggers commented out). Nothing compares commanded motion to actual displacement. And the doc's own stuck definition ("position hasn't changed") is circular without a position source.
3. **No HTTP endpoints on the BiBoard.** `GET /api/robots/bittle/position` does not exist and never will over serial; position must be synthesized host-side.
4. **The doc's §7 "Leash" is unimplementable** — it consumes a *user position* that no sensor in the system produces. Cut it from the MVP entirely.

## 3. The corrected MVP architecture (stock firmware, adapter-side odometry)

**Position = dead reckoning in the adapter**, fusing what we actually have:

- **Heading:** poll `gp` (~2 Hz) between motion commands — this slots perfectly into our existing serial transaction lock; **do not use the continuous `gP` stream in the MVP**, because unsolicited `ICM:` lines interleaving with command echoes would force a redesign of the adapter's locked write→echo reader (a real project on its own; `reset_input_buffer()` would eat stream data between transactions).
- **Advance:** command `kwkF <n cycles>`, wait for the completion echo, then advance the estimate by `n × stride_per_cycle` along the current yaw. `stride_per_cycle` is calibrated once with a tape measure (walk 10 cycles, measure). Same for `kbkF`.
- **Turns:** `kwkL/R <deg>` (closed-loop, firmware-verified yaw) or `kvtL/R` bursts + `gp` readback.
- **Roam loop (adapter):** repeat { advance a bounded burst → `gp` → record point → turn a bounded random angle when the estimate approaches the user-drawn boundary polygon }. Keep `z` (random mind) OFF — it injects fidgets; note the firmware's power-saver forces `krest` after 60 s idle, so the loop must keep commands flowing or pause recording.
- **Trail recorder:** as designed in the doc, but adapter-internal (the sampling loop feeds it directly — the doc's HTTP `POST /trail/record` from the *browser* is the wrong direction; the GUI should only start/stop/watch).
- **Storage:** SQLite via the adapter's existing `models.py` (two tables: `locations`, `trails`, JSON columns for shape/objects/path). The doc's Postgres `POLYGON`/`POINT` types buy nothing at this scale; orchestrator Postgres can become the fleet-level store in a later phase.
- **GUI:** orchestrator-served vanilla page (like control/builder — not the doc's standalone React/`localhost:15001` HTML): SVG room editor (draw polygon, place objects), live trail polyline via passthrough polling or a STOMP topic, rotate-to-align tool. All consistent with the established passthrough pattern.

**Trail quality expectation to set now:** yaw is drift-compensated but magnetometer-less, and stride length varies with surface (carpet vs laminate — the firmware even ships a `carpet` gait). On a room-sized space expect the trail to be *topologically* right and metrically fuzzy; the doc's manual-alignment feature is well-conceived and should extend to a manual scale factor too.

## 4. Stuck detection — re-scope honestly

Options, in order of recommendation:

- **(a) Buy the Petoi RGB ultrasonic module.** The firmware *natively* supports it, including autonomous obstacle reactions (<5 cm → back away; 15–30 cm → steer) and a one-shot `XU trig echo` distance read. This converts "stuck detection" into "collision avoidance," which is strictly better, for ~€10–15 of hardware that's already first-class in the firmware. Recommended as the doc's Phase 2 opener.
- **(b) Custom firmware token.** The mining confirms a custom build is *cheap* (Arduino IDE, vendored libs, board defs already correct; ~30-line change to add a stuck/telemetry token; disable `WEB_SERVER` to drop the only external deps). Real, but a new maintenance surface — back up servo calibration offsets before any flash.
- **(c) Host-side heuristic** (accel-variance / yaw-anomaly during commanded gait) — plausible but unproven; treat as an experiment, not a committed feature.
- **MVP recommendation: ship Phase 1 without stuck detection.** Record the firmware's spontaneous `EXCEPTION:` lines (fall/knock/push) as trail event markers instead — they're free and real.

## 5. Firmware version risk — the first thing to verify

~~The mined snapshot is `B10_260820`; the robot runs `B10_251121` (~9 months older); the ⚠ features needed live verification.~~ **PROBED LIVE 2026-08-31 (on the mount) — all ⚠ features exist on `B10_251121`. No firmware update needed.** Results:

1. `gp` → `ICM: -0.18 -0.10 10.07 -288.0 -1.2 -0.7` — **ICM42670 confirmed**, format exactly as mined. Note: **yaw is continuous/unwrapped** (−288° observed) — the dead-reckoning parser must not assume ±180.
2. `g?` → `Gyro state: Update-1 Balance-1 Print-0 Frequency-1` — supported.
3. `kwkF 3` → `Cycle counting mode: 3 cycles, Period: 116` — **cycle mode supported**, but the `k` echo arrives immediately (0.28 s), NOT deferred: the adapter must treat the echo as "gait started" and detect completion via the `Cycle target reached, stopping gait` + `up`/`k` lines (confirmed printed over USB) or a computed wait (~1.3 s/cycle).
4. `kwkL 45` → `Started turning gait: wkL initial yaw: -249.83, target angle: 155.17, turning direction: LEFT (CW)` — **closed-loop turn mode arms correctly** (target wrapping to ±180 confirmed). Completion-on-target still needs the floor test (body can't rotate on the mount).
5. **Quirk discovered:** the earlier `kwkF 3` cycle counter, cut short by `kup`, **stayed armed** and fired during the later turning gait (`Completed cycle 1/3 … 3/3 → Cycle target reached → up`). So `kup` does not clear `cycleCountingMode` on this build — the adapter's roam loop must either let every bounded gait run to completion or expect a stale counter to trigger on the next gait. (Silver lining: this accidentally proved live that auto-stop + completion prints work.)

Remaining floor-only items: turn-completion via real yaw rotation, and the `stride_per_cycle` tape-measure calibration on the target surface.

## 6. Codebase-fit corrections (same class as previous reviews)

- All endpoints robot-scoped: `/api/robots/<id>/spatial/...`, not `/api/dog/...`; robot id is `bittle-1`.
- `/api/servo/walk|turn|stop` don't exist — motion goes through the existing controller (`send_command`) inside the roam loop; the GUI never commands motion directly.
- Roaming must be mutually exclusive with the behavior loop and the sequence builder — reuse the established 409-guard pattern (a "spatial session" is a third owner of the serial port; the transaction lock already serializes writes, the guard prevents interleaved *intent*).
- `datetime.utcnow()` is deprecated (use `datetime.now(timezone.utc)`); trail timestamps should be real epoch/ISO times, not sequence numbers.
- The doc's GUI JS records trail points browser-side *and* posts them to the adapter (two divergent copies) — single source of truth belongs in the adapter.
- Tests: the doc's "unit tests" hit live HTTP; write them as Flask test-client + fake-controller tests per the repo's existing pattern.

## 7. Safety note

Autonomous roaming + `z_height: 0.75` (desk) + **no cliff detection** = the dog walks off the table. Until an edge sensor exists, roaming happens on the floor or on the suspension mount only. (The firmware's lifted/dropped detection reacts *after* the fall, which is not the feature we want.)

## 8. Proposed re-scoped plan (≈1 week of sessions, not 4–5 weeks)

1. **Session A (needs dog):** the §5 firmware probe → decide stock-vs-update; measure `stride_per_cycle` on the target floor; capture real `gp` output for the parser fixture.
2. **Session B:** adapter — odometry/dead-reckoning module + roam loop (bounded bursts, boundary-aware turns, 409 guards) + trail recorder + SQLite tables + `/spatial/**` endpoints, all mock-testable.
3. **Session C:** orchestrator passthrough + map page (room polygon editor, live trail, stuck/exception markers, align/rotate/scale tool).
4. **Session D (needs dog):** live trail on the floor; tune stride/turn constants; evaluate trail quality against the drawn room.
5. **Phase 2 gate:** ultrasonic module (recommended) → collision avoidance + real stuck events; camera/LiDAR later per the doc.

## Open questions before implementation starts

1. **Firmware update appetite:** if the ⚠ primitives are missing on `B10_251121`, OK to flash the latest official firmware? (Standard Petoi flow; calibration backed up first.)
2. **Ultrasonic module:** worth ordering now? It's the cheapest path to real collision/stuck sensing and is fully supported by stock firmware.
3. **Roam surface:** floor confirmed as the test arena (per §7)?
4. **Voice module during trails:** OK to close it (`Xa`) while recording to keep the serial stream clean, re-enabling afterwards?
