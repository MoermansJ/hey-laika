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
| `BITTLE_COMMUNICATION_METHOD` | `mock` \| `serial` \| `wifi` |
| `AUTONOMOUS_INTERVAL` | Seconds between autonomous decisions |

`.env` is gitignored and excluded from the Docker image; secrets are injected
at runtime via `env_file`.

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
pytest tests/ -v
```

## Roadmap

Phase 0 (this) → 1: USB hardware → 2: display streaming → 3: LEDs →
4: WiFi module → 5: sensors → 6: polish → 7: cloud (Postgres/AWS).
See `BITTLE_PROJECT_SETUP.md` for the full plan.
