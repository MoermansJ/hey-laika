# Validation Results — 2026-08-30

**Executed by:** Claude Code, automated harness (single serial session, non-interactive)
**Hardware:** Bittle X V2, BiBoard, firmware `B10_251121`, COM3 via CH343 USB-serial
**Note:** The Petoi desktop app (Win_1.2.9) was holding COM3 and was closed to run these tests.
**Manual-eyes observations could not be performed** (no human watching the dog); those fields are marked PENDING with the machine evidence noted. Everything else is real captured data.

---

## Test Execution

### Test 1.3: DTR Reboot
- Servos went slack during serial open? **PENDING (eyes)** — but machine evidence says **NO REBOOT**: 0 bytes of boot chatter in 5 s after `open()`, and the first `j` returned the pre-existing session state (head 30°, legs 73/−57 — the pose from the earlier desktop-app session), not a boot-default posture.
- Moved to new posture? **NO** (state fully persisted across the app being killed and our port open)
- Firmware line endings observed: **`\r\n`** (every line; the echo-counter fix was necessary)
- **Conclusion: opening COM3 with pyserial defaults does NOT reboot this board.** Adapter restarts are safe.

### Test 1.1: Binary I Echo
- Echo `I` received? **YES**, single clean line `I\r\n`
- Time to echo: **0.147 s** (for a 33° move on joint 8)
- Angles correct immediately after echo? **YES** — joint 8 read 40° immediately, identical after 1 s settle
- Both joints updated? **YES** (head commanded 30 = its prior value; joint 8 went 73→40 and read back exactly 40)
- Motion appeared: **PENDING (eyes)** — but see Test 2.3: latency scaling proves firmware-interpolated motion
- **Conclusion: the echo is a COMPLETION signal, not a receive-ack** (see 2.3), and readback immediately after echo is already settled. `move_joints()` can be synchronous and truthful.

### Test 1.2: Concurrency
- Both commands executed cleanly? **NO — and this is the headline finding.**
- Sent `m0 20` + `j` back-to-back with no wait. Captured over 3 s: `m\r\n` only. **The `j` was silently DROPPED** — no echo, no angle lines, no garbling.
- Responses interleaved? **NO — worse: the second command is discarded while the firmware is busy executing the first.**
- Raw: `b'm\r\n'`
- **Conclusion: firmware does not queue commands. The adapter's serial lock must span the entire write→echo transaction, and the polling GET must never fire while a move is in flight — otherwise commands vanish without error.**

### Test 2.5: Calibration Offsets
- Got offset response? **YES**
- Calibration offsets (16 values): **`1, 0, 0, 0, 0, 0, 0, 0, −1, −3, −5, −2, −6, −9, 11, −2`**
- All zeros? **NO** — all 9 physical joints (0, 8–15) carry non-trivial offsets
- **Conclusion: calibration HAS been run.** The "calibrated" claim in the design doc is confirmed; no offset math needed in our code.
- Bonus protocol capture: response format is `calib` header line → tab-separated index row → comma+tab value row → `c` echo. Sending `a` (abort) printed `G` + `aborted` — calibration mode disables the gyro and abort re-enables it (`G`). Also observed unsolicited `XAd`/`XAc`/`X` lines around calibration — voice-module chatter that any parser must tolerate.

### Test 2.4: Commanded vs Measured (variant — command-while-passive)
- Ran the no-hands variant: `p` (passive) → `j` → `m0 15` while passive → `j`.
- Head angle before: 0° | After `m0 15` while passive: **`j` reported 15°**
- **Conclusion (near-certain): `j` reports COMMANDED/target state, not measured position.** The firmware updated its angle table to 15° for a servo that was powered off. Caveat: `m` might re-engage torque on that joint, which only eyes can rule out — the original hand-move test remains the 30-second definitive check. Combined with the hardware fact that these servos have no position feedback wire, treat readback as firmware-target state in the design doc.

### Test 2.1: j During Skill
- `kbalance` completed in ~0.5 s (it's a quick posture, not an 8 s gait) — echo format: skill name (`balance`) then **`k`** on its own line (skills echo the bare `k`, not the full token).
- The `j` sent at t+0.5 s executed cleanly at 0.522 s — it landed just as the skill finished. Given Test 1.2, a `j` landing mid-execution would have been dropped instead.
- Response quality: **clean** — and the post-balance readback showed all 8 leg joints at exactly 30° (the balance posture), with the phantom joints 1–3 zeroed.

### Test 2.2: p Power Toggle
- Echo was: **`P` (uppercase) — both times.** Not the desktop app's documented quirky `k`, and not lowercase `p`. Per the case-signals-state convention, `P` = servos off; getting `P` on both toggles is ambiguous, so the toggle state machine needs the 10-second eyes-on check (limp after first `p`, stiff after second).
- Servos went limp / re-tightened: **PENDING (eyes)**

### Test 2.3: Speed Control (echo-latency proxy)
- Measured echo latency vs move size on the head joint:
  | Move delta | Echo latency |
  |---|---|
  | 10° | 0.054 s |
  | 30° | 0.092–0.135 s |
  | 40° | 0.174 s |
- Latency scales ~linearly with distance (~4 ms/degree ≈ 250°/s) → **firmware interpolates the motion and echoes on completion.**
- Motion type: **smooth/interpolated** (by measurement; visual confirmation PENDING)
- Acceptable for slider drags? **YES** — no violent jumps; and the completion-echo gives natural pacing (drop intermediate slider values while a move is in flight rather than queueing them).

---

## Decisions (Confirmed by Data)

### D1: Autonomy Preemption — **A: kill the adapter's autonomous loop** (unchanged; already Phase 1b architecture). Add the 409 guard at the servo endpoint as a safety net.

### D2: Serial Locking — **Lock + loop removal, and the data raises the stakes.**
Test 1.2 shows unsynchronized commands aren't garbled — they're **silently lost**. The lock must wrap the full transaction (`write → await echo → parse`), and the GET-polling handler must coalesce/skip while a POST transaction holds the lock. A plain write-lock is not enough.

### D3: Deployment — **B: all native, H2 dev profile, waitress for Flask** (unchanged). Bonus from Test 1.3: since opening the port doesn't reboot the dog, the adapter can restart freely during development.

---

## Unknowns Closed

- [x] Binary `I` echo reliable? **Yes — and it signals completion, not receipt** (1.1, 2.3)
- [x] Servo position feedback exists? **Effectively no — `j` is firmware-target state** (2.4 variant; hand-move confirmation optional)
- [x] Calibration actually run? **Yes — non-zero offsets on all 9 joints** (2.5)
- [x] Serial locking needed? **Yes, transaction-scoped — firmware drops busy-time commands** (1.2)
- [x] Speed interpolation needed? **No — firmware interpolates at ~250°/s** (2.3)
- [x] DTR reboot on open? **No** (1.3)
- [x] Line endings: **`\r\n`** | Skill echo: **bare `k` after skill-name line** | `p` echo: **uppercase `P`**

## Remaining PENDING (eyes-on, ~2 minutes total, optional)
1. `p` toggle: confirm limp→stiff cycle (Test 2.2)
2. Hand-move head while passive to make 2.4's "commanded-only" verdict bulletproof
3. Watch one `I` move to sanity-check "smooth" visually

## Notes
- Session state fully persisted across desktop-app kill + our port open — the board is forgiving.
- Phantom joints 1–3 report garbage (−82/−47/−2) until a skill zeroes them; the GUI must ignore indices 1–7, not display them.
- Unsolicited `X…` (voice module) lines appear in the stream; the adapter's reader must skip unknown lines rather than error.
- The dog was left in `krest` posture; the Petoi desktop app was closed and not relaunched.
