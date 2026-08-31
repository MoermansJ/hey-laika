# Bittle Orchestrator

Spring Boot management platform for a fleet of robot instances. Each robot on
the platform is backed by its own Python adapter service (see `../dog`) that
implements the robot-specific hardware and AI logic; the orchestrator is a
thin coordination layer that registers robots, proxies commands, and serves
the (temporary) web UI.

**Stack:** Java 21 - Spring Boot 3.5 - Spring Data JPA - PostgreSQL - Docker

```
Browser -- http://localhost:8080  (static UI + REST API)
             |
     Orchestrator (this project)
     |- FleetManager        in-memory registry of RobotAgents
     |- RobotAgent          one per robot, delegates to its adapter
     |- PythonServiceClient HTTP client to the adapter services
     |- PostgreSQL          fleet metadata (robots table)
             |
     Python adapter service(s), one per robot  (../dog)
     |- /api/robots/{robotId}/...  -- hardware, Claude decisions, personality
```

## Run the full stack

```bash
cp .env.example .env       # add ANTHROPIC_API_KEY (or set DECISION_ENGINE=mock)
docker compose up --build
# open http://localhost:8080
```

Services: orchestrator (8080), python adapter for bittle-1 (host port 15001;
drives the robot over WiFi by default — set `MOCK_MODE=True` in `.env` to
simulate), PostgreSQL (host port 15432, `bittle`/`bittle`, db `bittle_fleet`),
Ollama (11434, local LLM for the voice feature).

Note: the adapter and postgres host ports are 15001/15432 because 5001 and
5432 fall in Windows excluded port ranges on this machine
(`netsh interface ipv4 show excludedportrange`).

## Local development

```bash
# needs a reachable PostgreSQL (docker compose up postgres) and the Python
# adapter reachable on port 15001 (docker compose up python-bittle-1)
./mvnw spring-boot:run
./mvnw test
```

## Configuring robots

Robots are declared in `application.yml` (or environment overrides) and synced
to the database at startup:

```yaml
bittle:
  robots:
    - id: bittle-1
      name: Bittle 1
      type: bittle_x_v2
      service-url: http://localhost:15001
```

Docker env equivalent: `BITTLE_ROBOTS_0_ID`, `BITTLE_ROBOTS_0_NAME`,
`BITTLE_ROBOTS_0_TYPE`, `BITTLE_ROBOTS_0_SERVICEURL` (increment the index for
additional robots, and add a matching Python service to `docker-compose.yml`).

## REST API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Orchestrator health + fleet size |
| `/api/fleet/robots` | GET | Registered robots |
| `/api/fleet/status` | GET | Status per robot (unreachable robots report `connected: false`) |
| `/api/fleet/stats` | GET | Fleet totals |
| `/api/fleet/autonomous/start` / `stop` | POST | Autonomous mode fleet-wide |
| `/api/robots/{id}/status` | GET | Proxied robot status |
| `/api/robots/{id}/personality` | GET | Personality state |
| `/api/robots/{id}/behavior` | GET | Ask Claude for one behavior decision |
| `/api/robots/{id}/command` | POST | Raw controller command `{"command": "kbalance"}` |
| `/api/robots/{id}/interact/{type}` | POST | `pet` / `play` / `talk` / `feed` |
| `/api/robots/{id}/choreography/list` | GET | Available animations |
| `/api/robots/{id}/choreography/execute/{name}` | POST | Run an animation |
| `/api/robots/{id}/autonomous/start` / `stop` / `status` | POST/GET | Autonomous behavior loop |
| `/api/robots/{id}/activity` | GET | Recent activity log |
| `/api/robots/{id}/display` | GET | What the robot is currently "saying" |

Adapter error responses (unknown animation, missing API key, ...) are
forwarded verbatim; an unreachable adapter yields `502 adapter_unavailable`.
