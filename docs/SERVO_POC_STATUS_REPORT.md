# Fleet Platform Status Report — Servo Control POC Planning

**Date:** 2026-08-30
**Scope:** Full assessment of the three sibling projects under `F:\projects\robot` (`orchestrator`, `dog`, `petoi`) to identify blockers and plan the end-to-end web-based servo control POC.

**TL;DR:** The software stack (orchestrator → adapter → mock) is real, tested, and running, but **no code has ever touched the physical robot** — the project is still hardware Phase 0. The good news: the serial command protocol, servo index map, and wire encoding have now been fully extracted from the official Petoi desktop app clone, and the existing raw-command passthrough means a servo command typed into the GUI would already reach the serial port today. The four hard blockers are listed in [§7](#7-blockers).

---

> ## ⚠ Addendum (2026-08-31): most blockers below are RESOLVED
>
> This report is a point-in-time snapshot; the following has changed since:
>
> - **Robot connected and validated live** — firmware `B10_251121` over USB serial on 2026-08-30 (`docs/VALIDATION_RESULTS.md`), so §1's "never been connected" and §5's "completely untested" no longer hold.
> - **Serial read path shipped** (blocker 2) — `SerialBittleController` is now a locked write→await-echo transaction engine with `j` readback and `?` handshake, covered by unit tests.
> - **WiFi controller rewritten to the real protocol** (blocker 4) — `WiFiBittleController` now speaks the WebSocket `ws://<ip>:81` JSON/`b64:` task protocol this report prescribes, validated live driving the robot (stand/wave/sit) on 2026-08-31.
> - **Docker deployment unblocked** (blocker 3) — the robot was provisioned onto WiFi (`w%SSID%password`, auto-reconnects each boot), so no COM passthrough is needed; compose passes `BITTLE_COMMUNICATION_METHOD=wifi` + `BITTLE_WIFI_HOST` to the adapter container.
> - **`execute_action` implemented adapter-side** (blocker 5) and `simulate-actions: false` flipped in `application.yml`.
> - **Controller tests exist** — `tests/test_serial_controller.py` and `tests/test_wifi_controller.py` (§5's "zero tests" is stale).
> - §8's recommended plan Steps 0–1 are completed work.

---

## 1. Hardware & Communication

### Bittle X V2 state
- **Firmware version: unknown — the robot has never been connected to any of this code.** `dog/CONTEXT.md` states "Phase 0 / Next session: Phase 1: assemble Bittle". There are no hardware-related commits, no captured logs, and the serial port config is the untouched placeholder default (`COM3`).
- No modifications are documented anywhere. The board is the **BiBoard (ESP32)**; the official desktop app auto-forces board type `BiBoard_V1_0` for Bittle X models (`petoi/pyUI/UI.py:151-155`), so that is the expected board revision.
- First action of the POC must be a firmware handshake: send `?` over USB serial — the reply is the model name line followed by the board version line (e.g. `BiBoard_V1_0`), parsed in `petoi/pyUI/PetoiRobot/ardSerial.py:785-800`.

### Current communication
- **Today: none (mock).** `MOCK_MODE=True` everywhere; the mock controller fakes battery/signal.
- `dog/app/bittle_controller.py` has a factory with three transports:
  - **`SerialBittleController`** — written but never exercised. pyserial at 115200 (hardcoded constructor default, no env var), writes `command + "\n"` in ASCII, 2s sleep for board reset. **Write-only: it never reads the serial response**, so no acknowledgement or state can come back.
  - **`WiFiBittleController`** — written for the *wrong protocol*. It does `GET http://{host}/cmd?c=<command>` (ESP8266-style; its own docstring says ESP8266). The actual Bittle X WiFi protocol, per the official app, is a **WebSocket on `ws://<ip>:81`** with JSON frames `{"type":"command","taskId":…,"commands":[…]}` and base64 (`b64:` prefix) for binary payloads (`petoi/pyUI/SkillComposer.py:94-231`). This controller would not work against real firmware.
  - Bluetooth: the BLE dongle just enumerates as another serial port — no special code path needed (confirmed in the Petoi app, which has none either).

### Command protocol documentation — now in hand
Yes — mined from `F:\projects\robot\petoi` (clone of PetoiCamp/DesktopAppRelease; `pyUI/PetoiRobot/` is the reference implementation). Key facts:

**Wire encoding** (`ardSerial.py:112-138`):
- Lowercase tokens → ASCII: `token + "arg1 arg2 … " + "\n"` (rounded ints, space-separated).
- Uppercase tokens → binary: `token + struct.pack('b'*n, args) + '~'` (signed int8 per arg; `W`/`C` use unsigned).
- Multi-char string tokens (`k<skill>`, `g…`, `w…`, `X…`, `z…`) sent verbatim as a line.
- **Writes must be chunked to 20 bytes with a 1 ms gap** (firmware serial buffer limit).
- Angles are int8, clamped to **−125…125**; larger values fall back to ASCII forms or use the `angleRatio=2` halving scheme.

**Servo-relevant tokens:**

| Token | Form | Meaning |
|---|---|---|
| `?` | ASCII | Query model + board version (the handshake) |
| `k<name>` | ASCII line | Run named skill (`kbalance`, `ksit`, `kwkF`, `krest`, …) |
| `m idx angle …` | ASCII | Move joint(s) **sequentially** |
| `i idx angle …` | ASCII | Move joints **simultaneously** (text form) |
| `I` + int8 pairs | binary | Simultaneous indexed joint move (preferred for GUI control) |
| `L` + 16 int8 | binary | Set **all** joints positionally in one frame |
| `j` / `j idx` | ASCII | **Read back** all / one joint angle |
| `c idx offset` / `s` / `a` | ASCII | Calibration offset (±25°) / save to EEPROM / abort |
| `d` | ASCII | Rest / shut down servos |
| `p` | ASCII | Toggle servo power (active/passive) |
| `b tone dur …` | ASCII | Beep |
| `gb` / `gB` | ASCII line | BiBoard gyro off / on |
| `gc` | ASCII line | IMU calibration ("Calibration done" on success) |

**Acknowledgement protocol:** the firmware **echoes the command token** when done. The reference reads lines until one matches the sent token (case-insensitive first char); everything before it is the response payload (`ardSerial.py:297-333`). Timeouts: 8s for `k`/`K`/`X`, 3s otherwise, 1s for `I`/`L`.

### Servo layout — confirmed
From `petoi/pyUI/PetoiRobot/commonVar.py:163-184` plus the calibrator's side-ordering logic:

| Index | Joint | Index | Joint |
|---|---|---|---|
| 0 | **Head pan (neck yaw)** | 12 | Knee — Left Front |
| 1–7 | *Not present on Bittle* (`NaJoints['Bittle'] = [1..7]`) | 13 | Knee — Right Front |
| 8 | Upper leg ("Arm") — Left Front | 14 | Knee — Right Back |
| 9 | Upper leg — Right Front | 15 | Knee — Left Back |
| 10 | Upper leg — Right Back | | |
| 11 | Upper leg — Left Back | | |

**Bittle X = 9 physical servos: index 0 + indices 8–15.** Indices 1–7 are placeholders that still occupy slots in every 16-value `L`/skill frame. Wiring photos: `petoi/pyUI/resources/Bittle_Wire.jpeg`, `rotationDirections.jpeg`.

---

## 2. Backend Implementation

### Java Spring Boot orchestrator (`orchestrator/`) — real, not stubs
Spring Boot 3 / Java 21 / Maven. Every handler does real work; the only simulated layer is `ActionExecutor` when `behavior.simulate-actions=true` (currently on).

- **`FleetController`** (`/api/fleet`): robot registry, parallel status sweep, fleet stats, fleet-wide autonomous start/stop.
- **`RobotController`** (`/api/robots/{id}/…`): pure passthrough to the Python adapter — status, personality, behavior, **raw `POST /command`**, interact, choreography, autonomous, activity, display. Marked legacy in the design doc but fully wired and used by the fleet console.
- **`BehaviorController`** (`/api/robots/{id}/behavior/**`, uncommitted): orchestrator-owned personality system — Phase 1 of `docs/PERSONALITY_SYSTEM_DESIGN.md` v1.1. Per-robot behavior loop thread (2.5s reflex cycle), rule-based decision engine, 15-action catalog with posture/energy gating, manual action queue that pre-empts autonomy, STOMP broadcast per cycle. 15 unit tests green.
- **Persistence:** one JPA entity (`robots` table, Postgres via `ddl-auto: update`). Personality state and decision history are in-memory only (Phase 4 is persistence).
- **WebSocket:** push-only STOMP on `/ws`; fleet + per-robot topics at 2/3/5s cadence plus `/topic/robot/{id}/behavior` per loop cycle.
- **Dev profile:** `application-dev.yml` (uncommitted) runs on in-memory H2 — no Docker/Postgres needed, the fastest POC harness.
- **Servo/joint modeling: none.** The finest-grained Java abstraction is a named action string + duration. No angle, joint index, or calibration field exists in any DTO or entity.

### Python Flask adapter (`dog/`) — real, mock-only, ~1000 LOC
- 14 endpoints under `/api/robots/<id>/…` (status, personality, behavior, **raw command passthrough**, interact, choreography, autonomous loop, activity, display) plus `/api/health`. All robot routes 404 on a mismatched robot id.
- Claude-powered personality engine (SQLite-backed state, conversation history, mock fallback). The adapter runs its **own** 15s autonomous loop — which will race the orchestrator's behavior loop until Phase 1b disables it.
- SQLite: 7 tables; DB on disk shows exactly one mock session's worth of data.
- Tests: 24, all green, all mock-path. **Zero tests for the Serial or WiFi controllers.**

### Code that talks to the BiBoard
Only `SerialBittleController` (write-only, unexercised) — see §1. The known-good skill tokens used by choreography (`kwkF`, `kvtR`, `ksit`, …) are flagged in the module docstring as **unverified against Bittle X V2 firmware**.

### REST API contracts
- **Orchestrator → adapter:** fully defined in `PythonServiceClient.java` (`{serviceUrl}/api/robots/{id}{path}`, 3s connect / 30s read timeouts) and implemented adapter-side — except **`POST /execute_action`** (`{action, durationMs, sequenceId}` → `{robotId, action, success, actualDurationMs, message}`), which exists in Java (client + DTOs, uncommitted) and in the design doc §8.1, **but has no adapter route yet**. This is the agreed Phase 1b work.
- **No servo/joint contract exists on either side.**

---

## 3. Integration Testing

- **Backend ↔ adapter (software E2E): works.** The compose stack (Postgres + adapter + orchestrator) runs, the fleet console drives the adapter live, STOMP telemetry flows.
- **Backend ↔ physical robot: completely untested.** No serial session has ever been opened against real firmware; every command ever "executed" went to the mock controller. Whether the backend can command the Bittle to move is unknown until the §7 handshake happens.

---

## 4. Knowledge Gaps

**Now closed (via the `petoi` reference clone):**
- ✅ Wire encoding (ASCII vs binary, terminators, int8 angles, 20-byte chunking)
- ✅ Token inventory incl. joint-level `m`/`i`/`I`/`L` and readback `j`
- ✅ Servo index → body part map for Bittle
- ✅ Ack protocol (token echo) and timeouts
- ✅ Serial parameters (115200 8N1) and the `?` handshake ritual
- ✅ WiFi transport (WebSocket `ws://<ip>:81`, JSON frames, `b64:` binary) and USB WiFi provisioning (`w%SSID%password`)
- ✅ Skill file format (header semantics, gait/posture/behavior frame layouts)
- ✅ How the official app controls the robot (this *is* the desktop app source)

**Still open:**
1. **No OpenCat firmware source** in any local repo — exact parser behavior, per-token argument bounds, and unexercised tokens (`M`, `T`, full `X`/`g` space) are unverified. Cloning `PetoiCamp/OpenCatEsp32` would close this.
2. **Per-joint mechanical angle limits and zero convention** — only the ±125 wire clamp and ±25° calibration range are known. Physical testing or firmware source needed before a GUI slider gets safe min/max values.
3. **No IMU orientation readback command** found in the desktop app (only calibrate/enable/disable). May exist in firmware (`gP` telemetry stream format is undocumented).
4. **BiBoard pinout / PWM channel map** — absent from the desktop app repo; lives in firmware/schematics. *Not needed* for serial-protocol servo control, only for firmware modification.
5. The mobile app specifically has not been reverse-engineered — but the desktop app covers the same protocol, so this gap is effectively moot.

---

## 5. Sensor & Telemetry

- **Servo position readback:** the protocol supports it (`j` / `j idx`), but **no code in `dog/` reads from the serial port at all** — `SerialBittleController` has no read path. This is the single biggest code gap for a closed-loop POC.
- **IMU (BiBoard has a 6-axis IMU):** unused. Only protocol-level knowledge exists (calibrate `gc`, enable/disable `gB`/`gb`). Design doc Phase 3 plans IMU posture re-sync and fall detection.
- **Other sensors:** back touch sensor (analog pin 38, 0–2400 bucketed by 600, per the reference app) and mic — nothing wired up. Adapter telemetry (`battery`, `signal`) is mock-only; real transports return `None`.

---

## 6. Environment & Tools

- **IDE:** IntelliJ IDEA (JetBrains MCP bridge active in Claude Code sessions).
- **OS:** Windows 10 Home; Docker Desktop with compose (host ports remapped — 15432/15001/8080 — due to Windows excluded port ranges).
- **Java side:** Maven, Spring Boot 3, Java 21; `dev` profile with H2 runs without Docker.
- **Python side:** venv with pyserial 3.5 installed, pytest (24 green tests), gunicorn in Docker.
- **Robot physically present:** no evidence it has ever been plugged in; all testing is mock. `.env` is stale (missing `ROBOT_ID`, `DECISION_ENGINE`; empty `ANTHROPIC_API_KEY` → live Claude behavior calls currently 503).

---

## 7. Blockers

1. **Hardware never validated.** Firmware version, boot handshake, and actual skill-token compatibility are all assumptions until `?` gets a reply over USB. *(Mitigation: 10-minute smoke test with the official desktop app or a 5-line pyserial script.)*
2. **No serial read path.** `SerialBittleController` is fire-and-forget; without implementing the token-echo ack and `j` readback, the POC cannot confirm any servo actually moved.
3. **Docker on Windows cannot pass a COM port into a Linux container.** The adapter currently only ships as a compose container. For serial mode the adapter must run natively on the host (venv) — or the robot must be moved to WiFi. This changes the deployment story for the POC.
4. **The WiFi controller implements the wrong protocol** (HTTP GET vs the real WebSocket `:81` JSON protocol) and would need a rewrite before WiFi is an option.
5. Secondary: `execute_action` unimplemented adapter-side (orchestrator is waiting on it, `simulate-actions: true` until then); the adapter's own autonomous loop will race the orchestrator loop; serial-mode `/status` regresses (missing fields) the moment mock is off.

---

## 8. Recommended POC Plan — end-to-end servo control from the GUI

**Step 0 — Hardware smoke test (no code).** Plug in via USB, find the COM port, send `?` then `kbalance` then `m0 30` (head pan 30°) with the official app or a scratch pyserial script. Record firmware/board version. Closes blocker 1.

**Step 1 — Adapter serial layer (Python).**
- Add read support + token-echo ack to `SerialBittleController` (per `ardSerial.py:297-333` semantics), 20-byte write chunking, configurable port/baud via env.
- Add `POST /api/robots/<id>/servo` accepting `{"joints": [{"index": 0, "angle": 30}, …]}` → emit binary `I` (or ASCII `i`), clamp angles, validate indices against the Bittle map (0, 8–15).
- Add `GET /api/robots/<id>/servo` → `j` readback.
- Implement `POST /execute_action` (Phase 1b — orchestrator already ships the client) and disable the adapter's own loop when driven externally.
- Run the adapter natively on the host for serial access; keep Postgres/orchestrator in Docker.

**Step 2 — Orchestrator passthrough (Java).** `ServoCommandRequest`/`ServoStateResponse` DTOs, `POST/GET /api/robots/{id}/servo` proxied via `PythonServiceClient`, manual-queue integration so servo commands and the behavior loop never race (the manual-pre-emption mechanism already exists in `RobotBehaviorLoop`).

**Step 3 — GUI (static frontend).** A pose panel on the robot detail page: 9 sliders (head pan + 8 leg joints) laid out on the existing SVG blueprint from `specs.js`, debounced sends, live readback via a new STOMP topic or polling. `krest`/`kbalance`/servo-power buttons as safety controls.

**Shortcut that works today:** the fleet console's raw-command box → `POST /command` → adapter passthrough → serial write. Typing `m0 30` there would move the head the moment the adapter runs in serial mode — useful for step 0/1 verification before any new endpoint exists.
