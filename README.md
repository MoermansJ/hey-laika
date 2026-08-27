# Bittle AI Companion

Management system for an AI-powered robot dog (Petoi Bittle X V2). Claude makes
autonomous behavior decisions through a persistent personality engine; all
state, decisions, and interactions are stored in a database. Phase 0 runs
entirely in **mock mode** — no hardware and no API key required.

**Stack:** Python 3.11+ · Flask · SQLAlchemy 2 · Anthropic SDK · SQLite · Docker

## Quick start (Docker)

```bash
docker compose up --build
# open http://localhost:5000
```

## Quick start (local Python)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m app.app
# open http://localhost:5000
```

## Configuration

Copy `.env.example` to `.env` and edit. Key settings:

| Variable | Meaning |
|---|---|
| `DECISION_ENGINE` | `claude` (default — requires `ANTHROPIC_API_KEY`, raises a missing-credentials error without it) or `mock` (explicit offline simulation) |
| `ANTHROPIC_API_KEY` | Required when `DECISION_ENGINE=claude` |
| `CLAUDE_MODEL` | Model for decisions (default `claude-opus-5`) |
| `MOCK_MODE` | `True` = no hardware needed |
| `BITTLE_COMMUNICATION_METHOD` | `mock` \| `serial` \| `wifi` |
| `AUTONOMOUS_INTERVAL` | Seconds between autonomous decisions |

`.env` is gitignored and excluded from the Docker image; secrets are injected
at runtime via `env_file`.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | System status |
| `/api/personality` | GET | Personality state |
| `/bittle/status` | GET | Hardware status |
| `/api/personality/behavior` | GET | Ask for one behavior decision |
| `/api/personality/interact/<type>` | POST | Log interaction (`pet`, `play`, `talk`, `feed`) |
| `/api/choreography/list` | GET | List animations |
| `/api/choreography/execute/<name>` | POST | Execute animation |
| `/api/autonomous/start` / `stop` / `status` | POST/GET | Autonomous behavior loop |
| `/api/activity` | GET | Recent activity log |
| `/` | GET | Control dashboard |
| `/display` | GET | Phone/projector display (polls `/current`) |

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
