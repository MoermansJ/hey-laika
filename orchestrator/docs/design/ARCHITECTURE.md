# Orchestrator architecture

The Java orchestrator follows clean architecture. Code carries no Javadoc or comments;
everything a reader needs to know that is not visible in the code itself lives here or in
the other documents under `docs/`.

## 1. Layers and dependency rule

```
infrastructure  ->  adapter  ->  application  ->  domain
```

Dependencies point inward only. `ArchitectureTest` (ArchUnit, plain JUnit `check` calls)
fails the build on any violation. Rules enforced:

| Rule | Meaning |
|---|---|
| Layered | `infrastructure` is accessed by nobody; `adapter` only by `infrastructure`; `application` only by `adapter` and `infrastructure`; `domain` by everyone above it. |
| Domain is pure Java | `domain..` depends only on `java..` and `domain..`. |
| Application is framework-free | `application..` depends only on `java..`, `org.slf4j..`, `domain..`, `application..`. No Spring, Jackson, JPA or Micrometer. |
| Use-case shape | Every class in `application.usecase` ends in `UseCase`, is a top-level concrete class, and has exactly one public method, `execute`. |
| Inbound adapters call use cases | `adapter.in..` never depends on `application.service..`. |
| Adapters are independent | No `adapter.<in/out>.<x>` package depends on another. |
| Infrastructure is a leaf | No class outside `infrastructure..` depends on it. |

### Package map

| Layer | Package | Contents |
|---|---|---|
| Domain | `domain.behavior` | Personality model, action catalog, decision engine, behavior records. |
| | `domain.fleet` | `Fleet` (the immutable configured set of robots), `Robot` identity, `RobotInfo`, `FleetStats`, `RobotNotFoundException`. |
| | `domain.robot` | Records mirroring the Python adapter's JSON (`RobotStatus`, `ServoState`, ...). Field names match the adapter's camelCase exactly; Jackson maps them by name at both edges, so there are no mapper classes. |
| Application | `application.usecase` | One class per use case, `execute` only. The inbound API of the core. |
| | `application.service` | Collaborators shared by use cases: `FleetSweep`, `BehaviorLoops`, `RobotBehaviorLoop`, `ActionExecutor`, `OrchestratorMetricsSnapshot`. The only process-local state left here is the loop's worker thread, its manual-action queue and a bounded ring of recent decisions; everything durable goes through a port (§3, §7). |
| | `application.port.out` | Interfaces the core needs implemented: `RobotAdapterPort`, `FleetRepositoryPort`, `PersonalityStateRepositoryPort`, `DecisionHistoryRepositoryPort`, `LeasePort`, `EventPublisherPort`, `MetricsRollupRepositoryPort`, `OrchestratorMetricsPort`, plus the port exceptions `AdapterErrorException` and `AdapterUnavailableException`. |
| | `application` (root) | `BehaviorSettings`, `MetricsSettings`, `InstanceIdentity`, `BehaviorLoopRunningException`, `BehaviorLoopHeldElsewhereException`. |
| Adapters, inbound | `adapter.in.web` | REST controllers and `GlobalExceptionHandler`. |
| | `adapter.in.scheduling` | `FleetBroadcastScheduler`, `MetricsRollupScheduler`. |
| | `adapter.in.startup` | `FleetInitializer` (`ApplicationRunner`). |
| Adapters, outbound | `adapter.out.http` | `PythonAdapterHttpClient` implements `RobotAdapterPort`. |
| | `adapter.out.persistence` | JPA entities, Spring Data repositories, `FleetRepositoryAdapter`, `PersonalityStateRepositoryAdapter`, `DecisionHistoryRepositoryAdapter`, `LeaseRepositoryAdapter`, `MetricsRollupRepositoryAdapter`. |
| | `adapter.out.messaging` | `StompEventPublisher` implements `EventPublisherPort`. |
| | `adapter.out.metrics` | `MicrometerMetricsAdapter` implements `OrchestratorMetricsPort`. |
| Infrastructure | `infrastructure.config` | `@ConfigurationProperties` records, `RestClientConfig`, `WebSocketConfig`, `ApplicationConfig`. |

## 2. Use-case convention

- A use case is a concrete class named `<VerbPhrase>UseCase` with a constructor taking its
  collaborators and a single public method `execute(...)`. Helpers are private. Logic shared
  by several use cases lives in `application.service`.
- A use case may call another use case (`GetFleetStatsUseCase` and
  `BroadcastFleetStatusUseCase` both call `GetFleetStatusUseCase`, so one adapter sweep feeds
  status, per-robot status and stats).
- Wiring: `ApplicationConfig` declares
  `@ComponentScan(basePackages = "com.bittle.orchestrator.application.usecase", useDefaultFilters = false, includeFilters = REGEX ".*UseCase")`.
  Every use case is registered by constructor injection without any annotation. Supporting
  services and domain objects are explicit `@Bean` methods in the same class; `BehaviorLoops`
  uses `destroyMethod = "shutdown"` so loops stop on context close.
- Adding a feature: rules in `domain`, a `XxxUseCase` in `application.usecase`, outside-world
  access only through an interface in `application.port.out` implemented in `adapter.out`,
  and an inbound adapter that injects the use case. No config edit is needed for the use case.

## 3. Behavior loop (application.service)

- `BehaviorLoops` holds one `RobotBehaviorLoop` per robot, created lazily on first access;
  unknown robot ids raise `RobotNotFoundException` there. The personality state
  accepts events while the loop is stopped; it is then reloaded from the
  `personality_states` row first, so the database stays the source of truth.
- Ownership is a lease (`LeasePort`, key `behavior-loop:<robotId>`, owner
  `InstanceIdentity`, TTL `behavior.lease-ttl-ms`, default 60 s). `start()` acquires it or
  throws `BehaviorLoopHeldElsewhereException` (HTTP 409 `behavior_loop_held_elsewhere`);
  every cycle renews it and a cycle that cannot renew stops the loop; `stop()` releases it.
  Events, manual actions and `/execute_action` are refused while another live instance
  holds the lease. With one instance the lease costs one small update per cycle.
- State is single-writer, write-through: the lease holder loads the personality row and
  the latest `history-size` decisions once at start, keeps them in memory, and writes the
  row after every mutation. Readers on the holding instance are served from memory;
  readers anywhere else (and on this instance while the loop is stopped) read the
  database, which only happens on user requests, never on a schedule. Only decisions
  that selected an action (including rejections) are persisted; rest ticks live in the
  memory ring only, so the history endpoint shows rest ticks while the loop runs and
  action decisions once it has stopped. Persistence failures are logged and never stop
  the loop.
- The loop runs decide → execute → update on its own daemon thread named
  `behavior-<robotId>`. Each cycle drains the manual-action queue first, so manual control and
  autonomy never race on the servos. With the loop stopped, a manual action executes
  immediately on the caller's thread.
- The rule engine only returns actions valid for the current posture and energy
  (`Action.validFor`). The loop re-checks validity before executing and records a rejected
  decision otherwise.
- Cycle interval is `behavior.decision-interval-ms`, or `sleep-decision-interval-ms` while
  the robot sleeps. A failed action or a cycle exception backs off for
  `failure-backoff-ms`.
- After every cycle a `BehaviorUpdate` (decision + personality snapshot) is published to
  `/topic/robot/<id>/behavior`; publish failures are logged at debug and ignored.
- History keeps the last `behavior.history-size` decisions, newest first.
- `ActionExecutor` turns adapter failures into a failed `ActionResult` instead of an
  exception. With `behavior.simulate-actions=true` it sleeps for the action's duration and
  reports success without touching hardware.
- `PersonalityState` is not thread-safe; the loop's `stateLock` is the only guard, and the loop
  is the only writer.

## 4. Personality rules (domain.behavior)

- All six dimensions are clipped to `[0.0, 1.0]` after every mutation.
- Energy changes only through actions (and sleep recovery); there is no passive energy decay
  competing with recovery actions.
- Passive drift per cycle: boredom +0.01 while awake, curiosity +0.005 while awake, energy
  +0.05 while asleep, happiness −0.005 and hunger +0.01 when lonely (no owner interaction for
  `PersonalityStateManager.LONELINESS_THRESHOLD`, 30 s), contentment drifts 2 % toward 0.5.
- `SLEEP` additionally caps boredom at 0.3. `PICKED_UP` and `FELL_OVER` resync posture to
  `LYING` because the IMU says the assumed posture is gone.
- Rule engine priorities: sleeping robots rest until energy ≥ 0.55, then wake; energy < 0.15
  heads to sleep via lie-down; hunger > 0.8 and lonely seeks attention; boredom > 0.7 with
  energy > 0.5 plays (random pick among valid play actions); energy < 0.35 sits or idles; else
  the idle cycle when `behavior.idle-cycle=true`, otherwise `IDLE_CALM`.
- Idle cycle: sit → look around (low) → stand → stand a moment → look around (slow) → sit. The
  step is derived from (posture, last action), so it needs no stored state and self-heals from
  any entry point. A 0.3 linger probability lets sits, stands and looks chain to variable
  lengths. No stretch in the cycle.
- `Action` carries wire id, duration, valid starting postures, resulting posture (null =
  unchanged), personality impact and a minimum-energy gate. `Action.fromActionId` and
  `BehaviorEvent.fromName` are the only places wire names are parsed; unknown names raise
  `IllegalArgumentException`, mapped to HTTP 400.

## 5. Fleet, adapter and API notes

- Fleet of one: `Fleet` and `/api/robots/{id}` routing stay, but no genericity is
  added for hypothetical extra robots (see `OBSERVABILITY_MIND_BRIEF.md` §D). `Fleet` is
  built once from `bittle.robots` configuration and never changes at runtime; it is
  configuration, not a cache, so no request reads the `robots` table.
- `RobotAdapterPort` is the whole Python adapter surface. Typed calls map to `domain.robot`
  records. The untyped `get`/`post` relay carries host-side features (greeting, idle, power,
  polling, senses, leash, arbiter, behaviors, bindings, ears, mouth, eyes, mood) and the
  capability schema, so new adapter features need no orchestrator release. `getBinary`
  (`BinaryContent`) is the one non-JSON relay: the satellite camera frame at `/eyes/snap`,
  passed through with its content type and `Cache-Control: no-store`. Controllers whitelist
  the greeting and idle actions before relaying.
- `execute_action` is refused with HTTP 409 `behavior_loop_running` while the loop drives the
  robot. The loop check happens first (and resolves the robot), so 404 and 409 take
  precedence over adapter errors.
- Exception mapping (`GlobalExceptionHandler`): `RobotNotFoundException` → 404
  `robot_not_found`; `BehaviorLoopRunningException` → 409; `AdapterUnavailableException` →
  502 `adapter_unavailable` and the `bittle.adapter.unavailable` counter increments;
  `IllegalArgumentException` → 400 `bad_request`; `AdapterErrorException` forwards the
  adapter's own status and JSON body verbatim.
- HTTP client timeouts: 3 s connect, 30 s read, because choreography on real hardware sleeps
  through frame durations.
- Fleet status sweeps run in parallel across robots; an unreachable adapter yields
  `RobotStatus.unreachable` (connected = false) rather than an error. Fleet-wide autonomous
  start/stop map exceptions to `false` per robot.

## 6. Broadcasting

- `FleetBroadcastScheduler` counts STOMP sessions and only runs the broadcast use cases while
  at least one client is connected, so the adapters are not polled for nobody. An unmatched
  disconnect never pushes the count below zero.
- Cadence: status/stats every 4 s (halved from 2 s per owner request; with the adapter's 40 s
  telemetry TTL this keeps dog-facing traffic minimal), personality/display every 3 s,
  activity every 5 s.
- Topics: `/topic/fleet/status`, `/topic/fleet/stats`, `/topic/robot/<id>/status`,
  `/topic/robot/<id>/personality`, `/topic/robot/<id>/display`, `/topic/robot/<id>/activity`,
  `/topic/robot/<id>/behavior`. Per-robot broadcast failures are logged at debug and skipped.

## 7. Persistence and metrics

- `robots` table: fleet metadata mirrored from configuration. On boot `SyncFleetUseCase`
  deactivates robots that are no longer configured (kept for history) and upserts the
  configured ones as active. Nothing reads it back. Each repository call is its own
  transaction; read methods on every persistence adapter are `readOnly = true`.
- `personality_states` table: one row per robot, the loop's write-through copy of
  `PersonalityState` (§3). Upserted after every mutation, read on loop start, on idle
  events and by non-holding instances.
- `behavior_decisions` table: action decisions, newest by id. Every fiftieth append trims
  the robot's rows to `history-size`, so the table stays a few hundred rows.
- `leases` table: `lease_key`, `holder`, `expires_at`. `acquire` is a conditional update
  (same holder, or expired) followed by an insert when the row is missing; a lost insert
  race surfaces as a constraint violation and reads as "not acquired". The behavior loops
  and the hourly metrics rollup (`metrics-rollup`, 50 min) use it, so two instances never
  drive the same robot or write duplicate rollups.
- Not multi-instance yet: STOMP uses Spring's simple broker, so a push only reaches the
  browsers connected to the instance that produced it. A second instance needs a broker
  relay before its clients see the holder's decisions.
- `metrics_rollups` table: one snapshot per robot (plus `orchestrator`) per hour, kept
  permanently because hourly rows are tiny and the totals are accounting data
  (`OBSERVABILITY_MIND_BRIEF.md` §D.1). Snapshots are stored as JSON text; on read, an
  unparsable snapshot is returned as the raw string.
- Adapters measure exact token counts; only the orchestrator prices them
  (`metrics.claude-input-usd-per-mtok`, `metrics.claude-output-usd-per-mtok`, USD per
  million). `GetMergedMetricsUseCase` adds `estCostUsd` when Claude tokens are present.
- `OrchestratorMetricsSnapshot` owns the process start time so the live merge and the hourly
  rollup report the same uptime origin.

## 8. Testing conventions

- Test names follow `given<State>_when<Action>_then<Outcome>`. AssertJ everywhere; web slices
  use `MockMvcTester`; loops are replaced by streams and ranges where that reads better.
- `RobotControllerTest` declares every use case the controller injects with a class-level
  `@MockitoBean(types = ...)` and autowires only the ones it stubs.
- `LeaseRepositoryAdapterTest` is a `@DataJpaTest` slice on H2 with
  `@Transactional(propagation = NOT_SUPPORTED)`, so each adapter call commits on its own
  exactly as in production and the constraint-violation path is real.
- `ArchitectureTest` uses plain JUnit Jupiter with `ArchRule.check` rather than the ArchUnit
  JUnit 5 engine. Under this project's Surefire 3.5 / JUnit Platform 1.12 combination the
  engine discovered zero tests and silently passed a deliberately failing rule, so it cannot
  be trusted to guard the build.
