# Bittle Orchestrator — Application Overview

Context document for planning a GUI. Summarizes the architecture, domain model, DTOs, REST API, error contract, and current (temporary) web UI of this Spring Boot fleet orchestrator.

## What the app is

A management platform for a fleet of pet-like robots (Petoi Bittle quadrupeds). The orchestrator itself is a **thin coordination layer**: it registers robots from configuration, persists fleet metadata to PostgreSQL, and **proxies all robot-specific operations over HTTP to a Python adapter service per robot** (lives in `../dog`, outside this repo). The adapters own hardware control, personality simulation, and Claude-driven behavior decisions. The orchestrator holds almost no robot state — nearly every read in the UI is a live proxy call.

**Stack:** Java 21, Spring Boot 3.5, Spring Data JPA, PostgreSQL, plain static HTML/JS/CSS UI served from `src/main/resources/static/`. No frontend framework, no build step, no WebSockets — the current UI polls every 4 s.

```
Browser ── http://localhost:8080 (static UI + REST API)
              │
      Orchestrator (this repo)
      ├─ FleetManager         in-memory registry of RobotAgents (ConcurrentHashMap)
      ├─ RobotAgent           one per robot; knows only identity + adapter URL
      ├─ PythonServiceClient  RestClient wrapper for the adapter HTTP API
      └─ PostgreSQL           fleet metadata only (robots table)
              │
      Python adapter service(s), one per robot (../dog)
      └─ /api/robots/{robotId}/…   hardware, personality, Claude decisions
```

## Domain model

### Persistent entity (the only one)

`RobotEntity` → table `robots` (`model/RobotEntity.java`, Hibernate `ddl-auto: update`):

| Column | Type | Notes |
|---|---|---|
| `id` | Long | PK, identity |
| `robotId` | String | unique, not null — the public ID used in all API paths (e.g. `bittle-1`) |
| `name` | String | display name (e.g. "Bittle 1") |
| `type` | String | robot model (e.g. `bittle_x_v2`) |
| `serviceUrl` | String | base URL of the robot's Python adapter |
| `active` | boolean | false = removed from config, kept as history |
| `createdAt` / `updatedAt` | Instant | set by `FleetInitializer` |

The database is **write-mostly bookkeeping**. Runtime behavior is driven by the in-memory `FleetManager`, not by DB reads. `RobotRepository` (Spring Data JPA) has only `findByRobotId`.

### Runtime objects (not persisted)

- **`RobotsProperties`** (`@ConfigurationProperties(prefix = "bittle")`): list of `RobotDefinition(id, name, type, serviceUrl)` from `application.yml` / env vars (`BITTLE_ROBOTS_0_ID`, …). This is the source of truth for the fleet.
- **`FleetInitializer`** (ApplicationRunner): at startup, upserts each configured robot into the DB, marks no-longer-configured robots `active=false`, and registers a `RobotAgent` per configured robot with `FleetManager`. **There is no runtime add/remove API — fleet membership changes require a config change and restart.**
- **`RobotAgent`**: one per robot; wraps `PythonServiceClient` with the robot's definition. `statusOrUnreachable()` never throws (used for fleet overviews).
- **`FleetManager`**: `ConcurrentHashMap<String, RobotAgent>`; fan-out helpers `fleetStatus()`, `stats()`, and `forAll(action)` run over robots in parallel streams; per-robot failures degrade to `connected=false` / `false` rather than failing the whole call.

## DTOs (all in `dto/Dtos.java`, Java records)

These mirror the Python adapters' camelCase JSON exactly and are what the REST API returns — i.e. **this is the GUI's data vocabulary**:

- `RobotStatus(robotId, connected, mode, lastCommand, commandsSent, autonomous, mood)` — static factory `unreachable(robotId)` gives `connected=false`, all else null.
- `RobotPersonality(robotId, energy, happiness, boredom, curiosity, mood)` — the four traits are doubles on a 0–100 scale (the current UI renders them as percentage bars).
- `RobotBehavior(robotId, behavior, reason, source)` — one Claude behavior decision.
- `CommandRequest(command)` / `CommandResult(robotId, command, success)` — raw controller commands (e.g. `kbalance`).
- `InteractionResult(robotId, interaction, personality: Map<String,Object>)` — result of pet/play/talk/feed.
- `AnimationList(robotId, animations: [Animation(name, description, frames)])` and `AnimationResult(robotId, animation, success)`.
- `AutonomousState(robotId, running, changed, intervalSeconds)`.
- `ActivityLog(robotId, activity: [ActivityEntry(kind, message, at)])` — `at` is an ISO timestamp string.
- `DisplayContent(robotId, type, value, updatedAt)` — what the robot is currently "saying".
- `RobotInfo(robotId, name, type, serviceUrl, active)` — from the orchestrator's own registry (no adapter call).
- `FleetStats(totalRobots, connectedRobots, autonomousRobots, timestamp)` — timestamp is epoch millis.

## REST API

All under the orchestrator origin (port 8080); the static UI calls these same-origin.

**Fleet-level** (`FleetController`, `/api/fleet`) — served from the in-memory registry, with live fan-out where noted:

| Endpoint | Method | Returns |
|---|---|---|
| `/api/fleet/robots` | GET | `RobotInfo[]` (no adapter calls) |
| `/api/fleet/status` | GET | `Map<robotId, RobotStatus>` (parallel adapter calls; unreachable → `connected:false`) |
| `/api/fleet/stats` | GET | `FleetStats` |
| `/api/fleet/autonomous/start` / `stop` | POST | `Map<robotId, Boolean>` success per robot |

**Robot-level** (`RobotController`, `/api/robots/{robotId}/…`) — every call proxies to that robot's adapter:

| Endpoint | Method | Returns |
|---|---|---|
| `/status` | GET | `RobotStatus` (throws if unreachable, unlike fleet status) |
| `/personality` | GET | `RobotPersonality` |
| `/behavior` | GET | `RobotBehavior` — asks Claude for one decision (side-effectful/slow; treat as an action, not a poll) |
| `/command` | POST `{"command":"…"}` | `CommandResult` |
| `/interact/{type}` | POST | `InteractionResult`; types: `pet`, `play`, `talk`, `feed` |
| `/choreography/list` | GET | `AnimationList` |
| `/choreography/execute/{name}` | POST | `AnimationResult` |
| `/autonomous/start` / `stop` | POST | `AutonomousState` |
| `/autonomous/status` | GET | `AutonomousState` |
| `/activity` | GET | `ActivityLog` (recent events) |
| `/display` | GET | `DisplayContent` |

**Health:** `GET /api/health` → `{status, service, fleetSize, timestamp}`. Actuator exposes `health,info,metrics`.

### Error contract (`GlobalExceptionHandler`)

- Unknown robot → **404** `{"error":"robot_not_found","message":…}`
- Adapter unreachable (connection refused/timeout) → **502** `{"error":"adapter_unavailable","message":…}`
- Adapter returned an error (unknown animation, missing Anthropic API key, …) → the adapter's **status code and JSON body forwarded verbatim** (`AdapterErrorException`). So the GUI must tolerate error bodies of varying shape; current UI reads `body.message || body.error`.

## Current UI (the thing to replace)

`static/index.html` + `app.js` + `style.css` — single-page dashboard, explicitly labeled temporary:

- Polls `tick()` every **4 s**: fleet robots + stats + statuses, plus the selected robot's status/personality/display/activity in parallel.
- Layout: fleet stat line, robot cards (connection dot, name, id, type, mood) with click-to-select; a detail panel with connected/mood/mode chips, speech bubble (`display.value`), personality bars (energy/happiness/boredom/curiosity as % widths), interaction buttons (`data-interact` = pet/play/talk/feed), animation buttons from `/choreography/list`, autonomous toggle, "behavior once" button, raw command input, activity feed (last 30 entries), and toast notifications for action results/errors.

## Configuration & running

- Robots declared in `application.yml` under `bittle.robots` (or `BITTLE_ROBOTS_<n>_*` env vars). Current config: one robot, `bittle-1`, type `bittle_x_v2`, adapter at `http://localhost:15001`.
- Postgres: `jdbc:postgresql://localhost:15432/bittle_fleet`, user/pass `bittle`/`bittle` (compose service; overridden in Docker via `SPRING_DATASOURCE_URL`).
- **Windows port quirk:** adapter and Postgres host ports are 15001/15432 because 5001/5432 fall in this machine's excluded port ranges.
- Full stack: `docker compose up --build` (needs `ANTHROPIC_API_KEY` in `.env`, or `DECISION_ENGINE=mock`). Local dev: `./mvnw spring-boot:run`, tests via `./mvnw test` (MockMvc controller tests + FleetManager unit tests exist).

## Constraints & notes relevant to a GUI plan

1. **No push channel.** No WebSocket/SSE — live data requires polling (or adding a push mechanism server-side).
2. **Reads are live proxies.** Each robot-detail read hits the Python adapter; latency and 502s are normal operating conditions, not edge cases. Fleet endpoints degrade gracefully; robot-scoped endpoints throw.
3. **Fleet membership is static at runtime** (config + restart). A GUI for adding/removing robots would need new orchestrator endpoints.
4. **No auth** anywhere.
5. **The UI is served by Spring** from `static/`; same-origin API, no CORS config exists. A separate frontend dev server would need CORS or a proxy.
6. **`GET /behavior` triggers a Claude call** on the adapter — costs money/time; don't put it in a polling loop.
7. Field-naming: adapter JSON is camelCase and DTOs mirror it 1:1; `ActivityEntry.at` and `DisplayContent.updatedAt` are strings, `FleetStats.timestamp` is epoch millis.
