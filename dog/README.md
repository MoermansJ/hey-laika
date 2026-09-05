# Bittle AI Companion — Robot Adapter Service

Python adapter service for ONE AI-powered robot dog (Petoi Bittle X V2,
"Laika"). It owns the hardware transport, a single motion arbiter, stored
behaviors and event bindings, the leash/senses/power watchdogs and the voice
MVP; the orchestrator's personality loop drives it through `/execute_action`.
All state, decisions and interactions are stored in SQLite. Drives **real
hardware over WiFi by default**; set `MOCK_MODE=True` to simulate without a
robot (no API key is required either way — the decision engine defaults to
local Ollama).

This service is one robot instance's hardware/AI adapter in a fleet managed by
the Java orchestrator (`../orchestrator`). It has **no UI** — the orchestrator
serves the frontend and addresses this service via `/api/robots/<ROBOT_ID>/...`.
Run the full stack with `docker compose up` from `../orchestrator`.

**Stack:** Python 3.11+ · Flask · SQLAlchemy 2 · Anthropic SDK · SQLite · Docker

## Quick start (standalone, local Python)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m app.app
# API at http://localhost:5000/api/health
```

## Configuration

Copy `.env.example` to `.env` and edit. Key settings:

| Variable | Meaning |
|---|---|
| `ROBOT_ID` | Identity of the robot this service adapts (default `bittle-1`); requests for other ids get 404 |
| `DECISION_ENGINE` | `ollama` (default — local model, zero cost, falls back to one mock decision on transient failure), `claude` (requires `ANTHROPIC_API_KEY`, raises a missing-credentials error without it) or `mock` (explicit offline simulation) |
| `ANTHROPIC_API_KEY` | Required when `DECISION_ENGINE=claude` |
| `CLAUDE_MODEL` | Model used only when `DECISION_ENGINE=claude` (default `claude-opus-5`). The decision engine defaults to Ollama; Claude is opt-in |
| `MOCK_MODE` | `True` = no hardware needed (default `False`: real robot over WiFi). `MOCK_RICH=True` adds synthetic RSSI/scans/battery for GUI work |
| `BITTLE_COMMUNICATION_METHOD` | `mock` \| `serial` (USB) \| `wifi` (WebSocket to the BiBoard's stock firmware) |
| `BITTLE_WIFI_HOST` / `BITTLE_WIFI_PORT` | BiBoard address for `wifi` mode (default port 81) |
| `BITTLE_SERIAL_PORT` / `BITTLE_SERIAL_BAUD` | USB port for `serial` mode (default `COM3` @ 115200) |
| `OLLAMA_URL` / `OLLAMA_MODEL` / `OLLAMA_TIMEOUT` | Local LLM for the voice feature (defaults `http://localhost:11434`, `llama3.2:1b`) |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | Optional TTS for voice replies |
| `AUTONOMOUS_INTERVAL` | Seconds between autonomous decisions |

`.env` is gitignored and excluded from the Docker image; in compose, settings
are injected per-service via `environment:` entries interpolated from the
orchestrator repo's `.env`.

## API

All robot routes are scoped under `/api/robots/<robot_id>/` and return 404
unless `<robot_id>` matches this instance's `ROBOT_ID`. Responses use
camelCase keys to match the orchestrator's DTOs.

Generated from the routes in `app/app.py` (2026-09-02). Routes marked
*deprecated* are the old in-process brain, kept for the orchestrator's legacy
proxies and scheduled for removal (audit fix #11).

**Unscoped**

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Service health + identity (used by Docker/orchestrator probes) |
| `/metrics` | GET | Request/token metrics snapshot plus battery gauge, scraped by the orchestrator's metrics merge and hourly rollups |

**Status and telemetry** (`/api/robots/<id>/...`)

| Endpoint | Method | Description |
|---|---|---|
| `/status` | GET | Hardware status: connection, battery, posture, current arbiter behavior |
| `/power` | GET | Power-session tracker (on/off sessions, last snapshot) |
| `/polling` | GET / POST | Adaptive telemetry polling policy (read / configure) |
| `/schema` | GET | Capability schema (servos, actions, moves, transport) for UIs |
| `/activity` | GET | Recent activity log |
| `/display` | GET | *deprecated* — current display text |

**Motion**

| Endpoint | Method | Description |
|---|---|---|
| `/command` | POST | Raw controller token `{"command": "kbalance"}` (bypasses the arbiter) |
| `/servo` | GET | Commanded joint angles |
| `/servo` | POST | Move joints with the adapter's safety clamps (bypasses the arbiter) |
| `/execute_action` | POST | Execute a named high-level action plan; the orchestrator's behavior loop drives the hardware here |
| `/abort` | POST | Stop the current motion immediately (arbiter + controller), regardless of who started it |
| `/sound` | POST | Buzzer feedback patterns / tone sequence |
| `/choreography/list` | GET | List animations |
| `/choreography/execute/<name>` | POST | Execute an animation (bypasses the arbiter) |

**Behavior framework** (single arbiter owns motion; see `orchestrator/docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md`)

| Endpoint | Method | Description |
|---|---|---|
| `/behaviors` | GET / POST | List / upsert stored behaviors (step lists with priority and interruptibility) |
| `/behaviors/<name>` | GET | One stored behavior |
| `/bindings` | GET / POST | List / upsert event → behavior bindings |
| `/arbiter/status` | GET | What the arbiter is running, queue, last result |
| `/arbiter/invoke` | POST | Submit a behavior with a cause (provenance) |
| `/arbiter/stop` | POST | Stop the current behavior (non-interruptible ones finish) |
| `/greeting` | GET | Boot-greeting status (back-compat shim over the framework) |
| `/greeting/run` / `enable` / `disable` | POST | Run the greeting now / toggle it |
| `/idle` | GET | Idle-ladder status (sit → rest) |
| `/idle/enable` / `disable` | POST | Toggle the idle ladder |

**Leash and senses**

| Endpoint | Method | Description |
|---|---|---|
| `/leash` | GET | Proximity-leash state: RSSI, zone, dead-man, marks |
| `/leash/config` | POST | Enable/disable and thresholds |
| `/leash/mark` | POST | Record a labelled RSSI mark |
| `/senses` | GET | Senses layer status: WiFi sniffer, dead-reckoned pose |
| `/senses/samples` | GET | Fingerprint samples, newest first, with the live pose and `matched`/`total` counts. Filters: `?since=`/`?until=` (epoch s), `?source=auto|manual`, `?minAps=`, `?every=N` (keep one in N), `?limit=` (≤2000) |
| `/senses/pose/reset` | POST | Re-anchor the dead-reckoned origin at the dog's current spot (`{"heading"}` optional) |
| `/senses/range` | GET | Ultrasonic read (`?pin=9|10` to validate wiring; default `ULTRASONIC_PIN`), throttled to one firmware read per 150 ms, with `readMs`, `reads`/`misses` counters and the last 60 readings (`recent`, `null` = no echo) for the Eyes tab's live card |
| `/ears` | GET | Ears status: satellite PCM stream, whisper model, wake/utterance counters, `level` (DC-free RMS of the last packet, 1 s peak and median, the gate floor, whether the gate is open) |
| `/ears/transcripts` | GET | Recent transcripts (`?limit=`), wake flag and detected intent |
| `/ears/clip` | POST | Bench test: run an uploaded 16-bit mono WAV through the ears pipeline |
| `/mouth` | GET | Mouth status: speaker pin, TTS engine, last utterance |
| `/mouth/say` | POST | `{"text"}` → host TTS → 8 kHz PCM → firmware PWM on the Grove Speaker Plus |
| `/mouth/wav` | POST | Play an uploaded PCM WAV on the speaker (wiring check without TTS) |
| `/mouth/stop` | POST | Stop and flush speaker playback |
| `/mouth/sounds` | GET | Clip library: every WAV/MP3 in `dog/sounds` by name |
| `/mouth/play` | POST | `{"sound": "positive_bark"}` → the clip on the speaker (decoded once, cached) |
| `/satellite` | GET | The XIAO satellite's own status JSON (mic, camera, packets, rssi, led); 409 without `SATELLITE_HOST` |
| `/eyes` | GET | Eyes status: frame rate, cached-frame age, detector (model, loaded, confidence), persons in view, event counters |
| `/eyes/snap` | GET | Latest cached camera frame as `image/jpeg` (`?fresh=1` fetches a new one first) |
| `/eyes/config` | POST | `{"enabled"}` pauses/resumes frame grabbing |
| `/eyes/detect` | POST | Bench test: run an uploaded JPEG through the detector (events included) |
| `/mood` | GET | Mood light state: current/base mood, running flash, colour, satellite reachability |
| `/mood` | POST | `{"mood"}` pins a named mood; `{"mood","seconds"}` flashes it; `{"r","g","b","effect","periodMs","brightness"}` pins a custom colour |

The eyes need `models/yolov8n.onnx`; export it once with `tools/export_yolo.py`
(ultralytics + torch on the PC only, never in the image — onnxruntime is
already there for whisper's VAD).
| `/senses/sniff` | POST | One WiFi scan now (ignores the politeness clock; blocks ~2 s) |

**Gait learner**

| Endpoint | Method | Description |
|---|---|---|
| `/gait/start` | POST | Start a supervised learning session (moves the robot in batches) |
| `/gait/status` | GET | Session state, current trial |
| `/gait/continue` | POST | Operator confirms the robot is re-centred; next batch proceeds |
| `/gait/stop` | POST | Stop the session |
| `/gait/model` | GET | Learned stride/turn model |

**Voice**

| Endpoint | Method | Description |
|---|---|---|
| `/voice/health` | GET | Ollama reachability + model availability |
| `/voice/demo` | POST | "Hey Laika" text interaction: text in, LLM reply out, buzzer feedback |
| `/voice/speak` | POST | Standalone TTS: text → MP3 under `/static/responses/` |

**Deprecated old brain**

| Endpoint | Method | Description |
|---|---|---|
| `/personality` | GET | *deprecated* — adapter-side personality state |
| `/behavior` | GET | *deprecated* — one decision from the adapter's engine (Ollama default, Claude opt-in) |
| `/interact/<type>` | POST | *deprecated* — log interaction (`pet`, `play`, `talk`, `feed`) |
| `/autonomous/start` / `stop` / `status` | POST/GET | *deprecated* — in-process autonomous loop |

## Architecture

```
Flask (app/app.py)          — composition root: controller, arbiter, watchdogs, routes
 ├─ bittle_controller.py    — mock / serial / wifi (WebSocket) hardware transports
 ├─ arbiter.py + behavior_store.py + event_binder.py — single motion owner, stored behaviors, bindings
 ├─ greeting.py / idle_keeper.py / leash.py / senses.py / power.py — lifecycle watchdogs
 ├─ gait_learner.py         — supervised stride/turn calibration sessions
 ├─ personality_engine.py   — decision engine (Ollama default, Claude opt-in, mock); deprecated in-process brain
 ├─ voice.py                — Ollama text chain + TTS
 └─ models.py               — SQLAlchemy models (SQLite)
```

Runs under gunicorn with `--workers 1` on purpose: the module-level singletons
(controller, arbiter, watchdog threads) and the firmware's two-client
WebSocket cap both assume a single process.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Roadmap

Phases 0–1b, the WiFi transport and the behavior framework Phase 1 are
**done**: hardware validated over USB serial, then moved to the BiBoard's
onboard WiFi (WebSocket, no extra module needed); firmware is now the
hey-laika fork (base B10_251121, see
`orchestrator/docs/design/FIRMWARE_RESET.md`). Next: the adapter items in
`orchestrator/docs/reports/AUDIT_2026-09-02.md` §8, then voice hardware
(`VOICE_RELAY_BRIEF.md`) and navigation (`NAVIGATION_MAPPING_BRIEF.md`). See
`BITTLE_PROJECT_SETUP.md` for the original plan and `CONTEXT.md` for current
state.
