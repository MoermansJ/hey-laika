# Bittle AI Companion — Robot Adapter Service

Python adapter service for ONE AI-powered robot dog (Petoi Bittle X V2). Claude
makes autonomous behavior decisions through a persistent personality engine;
all state, decisions, and interactions are stored in a database. Runs in
**mock mode** by default — no hardware and no API key required.

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
| `DECISION_ENGINE` | `claude` (default — requires `ANTHROPIC_API_KEY`, raises a missing-credentials error without it) or `mock` (explicit offline simulation) |
| `ANTHROPIC_API_KEY` | Required when `DECISION_ENGINE=claude` |
| `CLAUDE_MODEL` | Model for decisions (default `claude-opus-5`) |
| `MOCK_MODE` | `True` = no hardware needed |
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

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Service health + identity (unscoped, used by probes) |
| `/api/robots/<id>/status` | GET | Hardware + autonomous status |
| `/api/robots/<id>/personality` | GET | Personality state |
| `/api/robots/<id>/behavior` | GET | Ask for one behavior decision |
| `/api/robots/<id>/command` | POST | Raw controller command `{"command": "kbalance"}` |
| `/api/robots/<id>/interact/<type>` | POST | Log interaction (`pet`, `play`, `talk`, `feed`) |
| `/api/robots/<id>/choreography/list` | GET | List animations |
| `/api/robots/<id>/choreography/execute/<name>` | POST | Execute animation |
| `/api/robots/<id>/autonomous/start` / `stop` / `status` | POST/GET | Autonomous behavior loop |
| `/api/robots/<id>/schema` | GET | Capability schema (servos, actions, moves) for UIs |
| `/api/robots/<id>/servo` | GET/POST | Read commanded joint angles / move joints |
| `/api/robots/<id>/execute_action` | POST | Execute a named high-level action plan |
| `/api/robots/<id>/sound` | POST | Play a buzzer tone sequence |
| `/api/robots/<id>/voice/health` | GET | Ollama reachability + model availability |
| `/api/robots/<id>/voice/demo` / `voice/speak` | POST | "Hey Laika" text interaction / TTS |
| `/api/robots/<id>/activity` | GET | Recent activity log |
| `/api/robots/<id>/display` | GET | Current display text (what the dog "says") |

## Architecture

```
Flask (app/app.py)
 ├─ personality_engine.py  — Claude (or mock) decides behavior; state persisted
 ├─ choreography.py        — animation library → command sequences
 ├─ bittle_controller.py   — mock / serial / wifi hardware adapters
 └─ models.py              — SQLAlchemy models (SQLite now, Postgres later)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Roadmap

Phases 0–1 and the WiFi transport are **done**: hardware validated over USB
serial (firmware B10_251121), then moved to the BiBoard's onboard WiFi
(WebSocket, no extra module needed). Remaining: display streaming → LEDs →
sensors → polish → cloud (Postgres/AWS), plus the personality director and
voice hardware. See `BITTLE_PROJECT_SETUP.md` for the original plan and
`CONTEXT.md` for current state.
