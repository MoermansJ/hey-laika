# Bittle Orchestrator

Spring Boot management platform for a fleet of robot instances. Each robot on
the platform is backed by its own Python adapter service (see `../dog`) that
implements the robot-specific hardware and decision logic; the orchestrator is
a thin coordination layer that registers robots, proxies commands, runs the
personality loop, and serves the web UI.

**Stack:** Java 21 - Spring Boot 3.5 - Spring Data JPA - PostgreSQL - Docker

## Architecture

Clean architecture, `infrastructure -> adapter -> application -> domain`,
enforced by ArchUnit rules that fail the build. The authoritative description
(package map, use-case convention, behavior loop, broadcasting, persistence,
testing conventions) is [docs/design/ARCHITECTURE.md](docs/design/ARCHITECTURE.md).
In six lines:

- `domain` is pure Java: personality model, action catalog, rule engine, fleet identity, and records mirroring the adapter's JSON by field name.
- `application.usecase` holds one `<Verb>UseCase` class per operation with a single `execute`; that package is the core's whole inbound API.
- `application.service` holds the stateful collaborators (`FleetRegistry`, `BehaviorLoops`/`RobotBehaviorLoop`, `ActionExecutor`); `application.port.out` holds the interfaces the core needs (`RobotAdapterPort`, repositories, `EventPublisherPort`, metrics).
- `adapter.in.*` are REST controllers, the STOMP broadcast/rollup schedulers and the startup fleet sync; `adapter.out.*` implement the ports over HTTP (Python adapter), JPA (Postgres), STOMP and Micrometer.
- `infrastructure.config` wires it: `@ConfigurationProperties` records, the `RestClient` (3 s connect / 30 s read), WebSocket, and a component scan that registers every `*UseCase` without annotations.
- Fleet of one by decision: `/api/robots/{id}` routing stays, but no genericity is added for a hypothetical second robot; `bittle-2` "Mocha" is a GUI fixture.

## Run the full stack

```bash
cp .env.example .env       # defaults to the local Ollama decision engine;
                           # set DECISION_ENGINE=claude + ANTHROPIC_API_KEY to opt in to Claude
docker compose up --build
# open http://localhost:8080
```

Services: orchestrator (8080); `python-bittle-1`, the adapter for Laika
(host port 15001; drives the robot over WiFi by default — set `MOCK_MODE=True`
in `.env` to simulate); `python-bittle-2`, the rich mock robot "Mocha"
(host port 15002; `MOCK_MODE=True MOCK_RICH=True`, synthesises leash RSSI,
WiFi scans and a draining battery — a GUI-development fixture, not a fleet
member); PostgreSQL (host port 15432, `bittle`/`bittle`, db `bittle_fleet`);
Ollama (11434, local LLM for the decision engine and the voice feature).

Note: the adapter and postgres host ports are 15001/15002/15432 because 5001
and 5432 fall in Windows excluded port ranges on this machine
(`netsh interface ipv4 show excludedportrange`).

## Trusted-LAN assumption

There is **no authentication** anywhere in this stack: the orchestrator's REST
API, the adapters' routes (including raw `/command`, servo writes and
calibration tokens), the STOMP endpoint and Postgres all accept any caller.
The stack is designed for one owner on a trusted home LAN, and the audit
(`docs/reports/AUDIT_2026-09-02.md` §2, §3, §7) records that as a deliberate
decision. Consequently **none of these ports may ever be port-forwarded,
exposed through a tunnel, or bound on an untrusted network.** If that ever
changes, add authentication first.

## Local development

```bash
# needs a reachable PostgreSQL (docker compose up postgres) and the Python
# adapter reachable on port 15001 (docker compose up python-bittle-1)
./mvnw spring-boot:run
./mvnw test

# standalone, no Docker: in-memory H2 + simulated actions
./mvnw spring-boot:run "-Dspring-boot.run.profiles=dev"
```

The test suite needs no database or adapter: it is unit tests, a `@WebMvcTest`
slice and the ArchUnit rules. CI (`../.github/workflows/ci.yml`) runs
`./mvnw -B test` and the adapter's `pytest` on every push and pull request.

## Configuring robots

Robots are declared in `application.yml` (or environment overrides) and synced
to the database at startup:

```yaml
bittle:
  robots:
    - id: bittle-1
      name: Laika
      type: bittle_x_v2
      service-url: http://localhost:15001
```

Docker env equivalent: `BITTLE_ROBOTS_0_ID`, `BITTLE_ROBOTS_0_NAME`,
`BITTLE_ROBOTS_0_TYPE`, `BITTLE_ROBOTS_0_SERVICEURL` (increment the index for
additional robots, and add a matching Python service to `docker-compose.yml`).

## REST API

Generated from the inbound web adapters in
`src/main/java/com/bittle/orchestrator/adapter/in/web/` (2026-09-02). Routes
marked *deprecated* belong to the adapter's old brain and are scheduled for
removal (audit fix #11). Routes marked *relay* forward to the same path on the
adapter without a typed DTO.

### `HealthController`

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Aggregated health: `{"status": "healthy\|degraded\|down", "service", "fleetSize", "robots": {id: {reachable, connected, name}}, "timestamp"}` — `degraded` when some adapters are unreachable, `down` when none are |

### `FleetController` — `/api/fleet`

| Endpoint | Method | Description |
|---|---|---|
| `/api/fleet/robots` | GET | Registered robots (`RobotInfo`) |
| `/api/fleet/status` | GET | Status per robot; an unreachable adapter reports `connected: false` instead of an error |
| `/api/fleet/stats` | GET | Fleet totals |
| `/api/fleet/autonomous/start` | POST | *deprecated* — start the adapter's legacy autonomous loop on every robot; `{id: true/false}` |
| `/api/fleet/autonomous/stop` | POST | *deprecated* — stop it on every robot |

### `RobotController` — `/api/robots/{id}`

| Endpoint | Method | Description |
|---|---|---|
| `/status` | GET | Proxied robot status (hardware, battery, connection) |
| `/personality` | GET | *deprecated* — adapter-side personality state |
| `/behavior` | GET | *deprecated* — one behavior decision from the adapter's own engine (Ollama by default, Claude opt-in) |
| `/command` | POST | Raw controller command `{"command": "kbalance"}` |
| `/interact/{type}` | POST | *deprecated* — log an interaction (`pet` / `play` / `talk` / `feed`) |
| `/choreography/list` | GET | Available animations |
| `/choreography/execute/{animation}` | POST | Run an animation |
| `/autonomous/start` / `/autonomous/stop` | POST | *deprecated* — adapter's legacy autonomous loop |
| `/autonomous/status` | GET | *deprecated* — its state |
| `/activity` | GET | Recent activity log |
| `/display` | GET | *deprecated* — what the robot is currently "saying" |
| `/capabilities` | GET | Adapter capability schema (servos, actions, moves) used by the GUI |
| `/servo` | GET | Commanded joint angles |
| `/servo` | POST | Move joints (`ServoMoveRequest`) |
| `/voice/demo` | POST | Text-in voice chain: LLM reply + buzzer feedback |
| `/voice/health` | GET | Ollama reachability + model availability |
| `/sound` | POST | Play a buzzer tone sequence |
| `/execute_action` | POST | Execute a named high-level action; `409 behavior_loop_running` while the orchestrator loop drives this robot |
| `/abort` | POST | Forward an abort to the adapter: stop the current motion immediately |
| `/greeting` | GET | *relay* — boot-greeting status |
| `/greeting/{run\|enable\|disable}` | POST | *relay* — whitelisted greeting actions; other names → `400 unknown_action` |
| `/idle` | GET | *relay* — idle-ladder status |
| `/idle/{enable\|disable}` | POST | *relay* — whitelisted idle actions |
| `/power` | GET | *relay* — power-session tracker |
| `/polling` | GET / POST | *relay* — adaptive telemetry polling policy (read / configure) |
| `/senses` | GET | *relay* — senses layer status (WiFi sniffer, dead-reckoned pose) |
| `/senses/samples` | GET | *relay* — recent sense samples |
| `/senses/sniff` | POST | *relay* — trigger one WiFi scan now |
| `/senses/range` | GET | *relay* — one-shot ultrasonic read (`?pin=`) |
| `/ears`, `/ears/transcripts` | GET | *relay* — satellite microphone status and recent transcripts |
| `/mouth`, `/mouth/say`, `/mouth/stop` | GET/POST | *relay* — speaker status, speak text on the dog, stop playback |
| `/leash` | GET | *relay* — proximity-leash state (RSSI, zone, dead-man) |
| `/leash/config` | POST | *relay* — leash thresholds / enable |
| `/leash/mark` | POST | *relay* — record a labelled RSSI mark |
| `/behaviors` | GET / POST | *relay* — list / upsert stored behaviors |
| `/behaviors/{name}` | GET | *relay* — one stored behavior |
| `/bindings` | GET / POST | *relay* — list / upsert event bindings |
| `/arbiter/status` | GET | *relay* — what the motion arbiter is running |
| `/arbiter/invoke` | POST | *relay* — submit a behavior to the arbiter |
| `/arbiter/stop` | POST | *relay* — stop the arbiter's current behavior |

### `BehaviorController` — `/api/robots/{id}/behavior` (orchestrator-owned brain)

| Endpoint | Method | Description |
|---|---|---|
| `/personality` | GET | Orchestrator personality snapshot (six dimensions, posture) |
| `/status` | GET | Loop running / last decision |
| `/history?limit=50` | GET | Recent decisions, newest first |
| `/start` | POST | Start the behavior loop for this robot |
| `/stop` | POST | Stop it |
| `/event/{type}` | POST | Apply a personality event (`BehaviorEvent` name); unknown → 400 |
| `/action/{action}` | POST | Queue a manual action through the loop (executes immediately when the loop is stopped) |

### `MetricsController`

| Endpoint | Method | Description |
|---|---|---|
| `/api/metrics` | GET | Merged live metrics (orchestrator + every adapter), with `estCostUsd` when Claude tokens are present |
| `/api/metrics/history?robotId=&limit=168` | GET | Hourly rollups for one robot (or `orchestrator`); limit clamped |

Adapter error responses (unknown animation, missing API key, ...) are
forwarded verbatim; an unreachable adapter yields `502 adapter_unavailable`.
STOMP push topics are listed in `docs/design/ARCHITECTURE.md` §6.
