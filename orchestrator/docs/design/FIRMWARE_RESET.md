# Firmware Reset — "CSS reset" for the BiBoard

**Date:** 2026-08-31 · **Status (updated 2026-09-02):** hey-laika fork flashed on
Laika. Phase A cuts 1, 3, 4 implemented; cut 2 partial (bounded WS queue exists,
its normal drain path is broken — audit §4 F1); cut 6 partial (`CAMERA` off,
`VOICE`/`QUICK_DEMO` still compiled, module defaults unchanged); cuts 5, 7, 8, 9,
10 not started. Leash/nav additions outside this list are also flashed: `XW`
tool set, 1 Hz `event_rssi`, second SSID slot, dead-man. Base version
**B10_251121** with the date pinned (cut 1), so the wire version still reads
`B10_251121`. Cut-by-cut evidence: `../reports/AUDIT_2026-09-02.md` §4.
**Source base:** `F:\projects\robot\opencat-esp32` (hey-laika fork, two commits over
upstream `9ebb48a` / B10_260820 snapshot; the robot reported stock B10_251121 before the fork)

## Rationale

Keep the machinery (gaits, servo control, IMU, WS/serial/BLE transports,
calibration); strip or gate every behavior the firmware initiates on its own.
The full source mapping (below) explains every anomaly from the calibration
sessions — none of them were mysteries, all are stock design choices:

| Live anomaly | Root cause (file:line) |
|---|---|
| Commands silently dropped mid-gait, yet reported success | `webServer.h:341-349` drops any new WS task while one is active (no reply at all for the new taskId); worse, the loop clobber race (`OpenCatEsp32.ino:86-95` + `taskQueue.h:76-95`) can drop a staged host command and then **falsely ACK it** when a queued task's echo fires (`reaction.h:1563-1566`) |
| `kvtL 45` spins forever | `kvt*` DOES take angle targets (any gait ending in L/R does — `reaction.h:1479-1495`), but the yaw-target check is the LAST `else if` in the IMU exception chain (`imu.h:882-901`) and vt gaits' pitch excursions constantly trip the LIFTED test (`ypr[1]>75`), starving the check → never stops |
| Abrupt "lay-down" after bounded gaits | Not a stop animation: the gait's pitch latches the LIFTED exception (suppressed while `period>1`), which fires the instant the queued `up` runs, loading the `dropped` crouch posture (`reaction.h:33-44`) |
| Auto-flip when off the mat | FLIPPED exception → `rc` recovery injected directly into the command slot (`reaction.h:57-69`), repeatedly (5ms exception task vs per-loop dispatch) |
| Yaw domain beyond ±180 with 360° jumps | ICM yaw = wrapped atan2 − accumulated `yawDrift`; the drift guard refuses ±180 folds (`petoi_icm42670p.cpp:230-234`) → unbounded output |
| Turns overshoot on fresh pack / auto-rest during sprints | Momentum (host-side concern) + low-battery watchdog forces `rest` below 7.0V sag (`reaction.h:234-341`, checked 1s) |

## The cut list (recommended order)

1. **Version pin (do FIRST, before any flash):** `OpenCat.h:80` `DATE → "251121"`.
   Otherwise `resetIfVersionOlderThan` (`configConstants.h:551-573`) triggers the
   new-board path: NVS rewrite (module list, BLE name), **blocking serial prompts**
   ("Reset joints' calibration? (Y/n)" waits forever with no USB attached), and a
   wrong keypress wipes servo calibration. Never define `AUTO_INIT` (silent wipe).
2. **Reliable command channel:** queue instead of drop in `webServer.h:341-349`
   (pending tasks already drain via `processNextWebTask`); fix the loop clobber
   (`readSignal()` unconditionally; `popTask()` only when the command slot is free).
   Kills both silent drops AND false ACKs.
3. **Reflexes behind a flag:** wrap the `dealWithExceptions` switch body
   (`reaction.h:32-169`) behind `imuReactQ` (default **off**, new sub-token under
   `T_GYRO`), replaced by a one-shot "exception report" line to the host.
   ⚠ Do NOT use `gyroBalanceQ` as the kill switch — it also disables gait
   balancing and gets force-reset to true in four places.
   This single cut removes: auto-flip, knock/push reactions, the fake "lay-down",
   free-fall response. Host decides recovery (tier-2 behavior in the adapter).
4. **De-latch the gait counters:** clear `cycleCountingMode/targetCycles/
   completedCycles/turningQ/needTurning` on every non-queue `T_SKILL` + on
   rest/abort; move the `turningQ` yaw check OUT of the exception else-if chain
   (`imu.h:882-936`) so vt/wk angle targets always evaluate → `kvtL 90` becomes a
   real firmware-closed-loop turn-in-place.
5. **Wrapped yaw:** wrap at the single assignment `petoi_icm42670p.cpp:234` to
   [−180,180); re-derive the near-180 turning special case from wrapped diffs.
6. **Idle life off:** delete the live `randomMind()/powerSaver()` call site
   (`moduleManager.h:530-533`) and the `z` token body; zero `moduleActivatedQ`
   defaults (`OpenCat.h:520`); drop `VOICE`/`CAMERA`/`QUICK_DEMO` defines
   (`OpenCatEsp32.ino:20-28`) — also removes the MuVisionSensor external dep.
   (Voice can be re-enabled later; runtime `Xv` also disables + persists.)
7. **Low-battery rest behind a token** (`lowBatteryRestQ`): `reaction.h:254-261`
   + `:336-338` — keep the warning prints, let the host decide.
8. **Honest completion everywhere:** extend `deferSkillTokenEcho` (already gives
   true motion-end completion for parameterized gaits incl. the blocking stand-up
   transform) to all `period != 1` skills with a guaranteed queued terminator.
   ⚠ every deferral MUST have a completion path or the WS task hangs 45s.
9. **Clean WS results:** `skill.h:60` skill-name print → serial-only; gate
   `print6Axis()` in the exception handler; drop the voice `X` echo (`voice.h:146`).
10. **Cosmetics:** expose `transformSpeed` (`skill.h:144`, hardcoded 1.0) via a
    token for gentle stand transitions; boot-time `T_SERVO_CALIBRATE`-on-exception
    (`OpenCat.h:768`) → unconditional `T_REST`.

## Build & flash

- **Toolchain:** Arduino (no platformio). `arduino-cli compile/upload`, FQBN
  `esp32:esp32:esp32` with UploadSpeed 921600 (fall back 460800), CPU 240MHz,
  QIO 80MHz, 4MB default+spiffs partition, PSRAM off. Serial monitor 115200.
- **External deps after the cut:** only `arduinoWebSockets` (Links2004) and
  `ArduinoJson` **v7** (v6 will not compile). Everything else is vendored.
- **Flash procedure:** USB tether; keep a serial terminal open on first boot in
  case any prompt path is reached. WiFi credentials survive (separate NVS
  partition); BLE name and module list survive only because of the version pin.
- **Before first flash:** read current calibration via the `c` token and record it.
- **Rollback:** reflash stock Petoi B10 release binaries over USB at any time.

## Phasing

- **Phase A (safety + reliability):** cuts 1–4. Small diffs, transforms the
  host-control contract: no drops, no false ACKs, no reflex motion, working
  turn-in-place-by-angle. Re-run the pinned calibration ladder on this build.
- **Phase B (quality):** cuts 5, 8, 9 — clean yaw, motion-end completion,
  parseable WS results. Deletes the adapter's wall-clock-wait workarounds.
- **Phase C (polish):** 6, 7, 10 as needed.
- **Tier 2 (future, separate design):** "blank" firmware — host streams joint
  frames, firmware only executes + reports sensors + safety-freezes on
  exception. Prototype only after Phase A/B proves the toolchain; it forfeits
  Petoi's tuned gait engine, so it should coexist, not replace.

## Risks

- Fork maintenance: upstream Petoi updates need manual merges (acceptable — the
  reference clone stays pristine for diffing).
- The B10_260820 base itself is newer than what we validated live; Phase A
  testing must re-verify the serial/WS protocol facts (`docs/robot/`).
- Deferred-echo hangs (cut 8) if any completion path is missed — pair every
  defer with a queued terminator, keep the 45s WS timeout as backstop.
