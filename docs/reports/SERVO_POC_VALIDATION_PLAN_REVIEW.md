# Review: Servo Control POC — Validation Action Plan

**Date:** 2026-08-30
**Reviewer:** Claude Code (against the mined Petoi protocol reference + actual codebase state)
**Verdict:** Plan structure is right — correct unknowns, correct tier split, sensible decision gates. Six issues in the test scripts need fixing before running against hardware (two will produce false failures, one is a physical safety risk), and two of the original unknowns have no test covering them.

---

## 1. Script bugs that will produce wrong results

### 1.1 Line-ending assumption breaks the echo counters (Tests 1.2, 2.1, 2.2) — FALSE FAILURE RISK
Tests count echoes with patterns like `all_data.count('\nm\n')`, `'\nj\n' in all_data`, `'\nk\n' in all_data`. OpenCat firmware output over serial typically uses `\r\n`. If so, every counter returns 0 and Test 1.2 falsely reports "responses interleaved/malformed" — the exact wrong conclusion for the most important concurrency decision. Fix: normalize first (`all_data = all_data.replace('\r\n', '\n')`) or match on stripped lines:

```python
lines = [l.strip() for l in all_data.splitlines()]
m_echos = lines.count('m')
```

### 1.2 Test 2.3 commands head to 120° — PHYSICAL SAFETY RISK
Per-joint mechanical limits are one of the *unknowns this plan exists to scope around*. The head pan very likely hits a mechanical stop well before 120°; a stalled 9g servo against a hard stop draws stall current and can strip gears. Use 60° for the speed observation — it is just as diagnostic for smooth-vs-instant, and safe. Same principle: nothing in any test should command beyond ±60° until limits are characterized.

### 1.3 Byte-wise echo loop can crash or false-match (Test 1.1)
`byte.decode()` on a non-ASCII byte raises `UnicodeDecodeError` (firmware boot noise / telemetry can contain them) — use `decode(errors='ignore')`. Also the loop breaks on *any* `I` character, and telemetry lines can contain capital I. Safer: accumulate into a buffer and check complete lines for a bare `I`.

### 1.4 Unguarded `[0]` on the angle-line filter (all tests that parse `j`)
`[l for l in lines if ',' in l][0]` raises `IndexError` if the response is short/garbled — which is precisely when you most need to see the raw data. Wrap with a fallback that prints `repr(all_data)` and continues, so a partial failure doesn't abort the whole session. (Also worth extracting the duplicated `j`-parse block into one helper — it appears five times and any fix must land in all of them.)

### 1.5 `ser.read(1000)` with `timeout=2` makes every read take the full 2 s
pyserial's `read(n)` blocks until n bytes **or** timeout; a `j` response is far under 1000 bytes, so every read stalls 2 s. Harmless for correctness, but it adds ~30–40 s across the session and, worse, in Test 1.1 step 4 ("read immediately after echo") it blurs the immediate-vs-settled distinction the test exists to measure. Prefer `timeout=0.3` with a read-until-idle loop, or `ser.read(ser.in_waiting)` polling.

### 1.6 Tests 1.1/1.2 baseline is post-reboot state
Opening COM3 at the top of each script triggers the same DTR reset Test 1.3 investigates, so the "current head angle" baselines in 1.1/1.2 are boot-posture readings, not continuations of prior state. Not a bug, but record it — and consider running Test 1.3 **first** so the reboot behavior is known before interpreting the other baselines.

---

## 2. Coverage gaps — two original unknowns have no test

### 2.4 (add): Does `j` report commanded or measured angles?
This was Tier-1 unknown #2 in the design review and it's absent here. It determines whether "readback keeps GUI in sync with robot state" is real feedback or an echo of firmware intent. Safe test (no servo strain): send `p` to make servos passive → physically move the head by hand ~30° → send `j` → does the reading change? Then `p` again to re-engage. If `j` doesn't track the hand-moved position, readback is commanded-state only, and the GUI's "live state" claim should be reworded in the design doc.

### 2.5 (add): Read stored calibration offsets
Design doc asserts "calibrated" and "no offset math needed" — unverified. One command closes it: send bare `c` (with no args it reads all offsets), record the 16 values, send `a` to make sure nothing enters calibration-save state. All-zero offsets on a hand-assembled robot would suggest calibration has *not* actually been run, which changes the "calibrated" claim in the deployment section.

---

## 3. Decision questions — recommendations

**D1 (autonomy preemption): A — kill the adapter's autonomous loop.** This isn't a new trade-off; it's already the agreed architecture. PERSONALITY_SYSTEM_DESIGN.md v1.1 §2.3 deprecates the adapter's `/autonomous/*` endpoints and makes the adapter execution-only, and Phase 1b explicitly includes disabling the adapter loop. Option A simply does Phase 1b's removal now. (Option C's 409 guard is a cheap *additional* safety net at the servo endpoint — worth having — but it's a complement, not the strategy.)

**D2 (serial locking): 1 AND 2 — the options are misframed as alternatives.** Option 2 (remove the autonomous loop) falls out of D1=A but is *insufficient alone*: the 500 ms polling GET and slider POSTs are still two concurrent writers hitting one COM port through Flask's threaded request handling. A `threading.Lock` around a single `_transact(command) → response` method in `SerialBittleController` is ~5 lines and non-negotiable. Note Test 1.2 does not change this conclusion either way: even if the *firmware* separates interleaved commands cleanly, the *adapter's* reader threads still race each other for bytes off the port. The lock is required regardless of the test result; the test only tells you how badly things degrade if the lock has a bug.

**D3 (deployment): B — everything native, H2 dev profile.** Fewest moving parts for the POC: no `host.docker.internal` indirection, no compose edits, one less network hop when debugging serial timing. One correction to Option A's text if it is chosen instead: the adapter's native port must match whatever `BITTLE_ROBOTS_0_SERVICEURL` says — the doc's `5001` is a third port convention alongside the container-internal `5000` and the established host mapping `15001`. Pick one (suggest `15001` for continuity) and state it once. Also note for B: Flask's dev server or waitress, not gunicorn (which doesn't run on Windows).

---

## 4. Minor corrections

- Header says "6 Tier 1 & Tier 2 unknowns" — the plan contains 3 + 3 tests, but with §2's additions it becomes 8. Renumber or reword.
- Test 2.1's `"kbalance" in all_data` will also match if the firmware echoes the command as typed before executing — treat a match as weak evidence and eyeball the raw dump.
- Test 2.2: per the reference implementation, expect the quirky `k` echo for `p`; if the echo turns out to be `p` on firmware B10_251121, note it — it means the desktop-app special-case is stale and ours doesn't need it.
- `VALIDATION_RESULTS.md` template: add fields for "firmware line endings observed (`\n` / `\r\n`)" and "calibration offsets (16 values)" — both feed directly into Step 1 implementation.

---

## 5. Suggested execution order

1. **Test 1.3 first** (DTR reboot) — its result contextualizes every other test's baseline.
2. Tests 1.1, 1.2 (with §1 fixes applied).
3. New Test 2.5 (calibration read — 30 seconds).
4. New Test 2.4 (commanded vs measured — needs `p` semantics, so run Test 2.2 immediately before it).
5. Tests 2.1, 2.3 (with the 60° cap in 2.3).

Time estimate stays realistic at ~60 min including the two added tests.
