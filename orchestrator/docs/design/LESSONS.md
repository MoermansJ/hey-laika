# Lessons — traps hit, and the decisions that came out of them

**Started:** 2026-10-15 · **Status:** living; append, don't rewrite

Things that cost real time to discover, written down so the next session
doesn't rediscover them. Each entry is the incident, then the rule. If a
lesson stops being true because the code moved, add a dated correction under
it rather than deleting it — the reasoning is usually still worth reading.

## Architecture

### 1. The arbiter queue is behavior-grained. Per-action detail lives in the action feed.

`arbiter.submit*()` enqueues one **submission**. Roaming and Fruitfly each
submit a single long-running generator (`navigate`, `fruitfly_drive`) that
yields steps internally, so an hour of Fruitfly driving is *one* queue entry
and *one* run-log row. Every individual decision it acted on — FORWARD, LEFT,
a route leg — existed nowhere: not in `queued`, not in `recentRuns`, not in
any API. Three separate attempts to show "the queue of generated actions"
failed for this one reason before it was named.

**Rule:** a per-decision view reads `dog/app/action_feed.py`, not the arbiter
queue. The arbiter pushes one feed entry per dispatched step
(`arbiter._feed_push`), tagged with the mode that caused it.

**Corollary — don't fix this by submitting more:** making each burst its own
`submit()` fights the design on three fronts: duplicate-name suppression
rejects same-named submissions already queued/running, the run log would
churn a row per second, and the generator pattern exists precisely so a
continuous driver can hold the arbiter and be preempted at step boundaries.

**If a generator wants a readable label**, yield one: `{"command": "kwkF",
"label": "FORWARD"}`. The feed shows the label and falls back to the raw
skill token. That is the only hook needed to make any future mode legible.

### 2. The briefs outrank an ad-hoc diagram. Check both against the code first.

Two documents in a row (a phone-call design doc, a Fruitfly architecture
diagram) placed a Signal Receiver, an Action Mapper and an SLF4J audit trail
in the **Java orchestrator**. None of it exists there, and none of it should:
`dog/app/arbiter.py` owns all motion, so routing a decision through Java and
back would be a redundant hop over a channel that was never built.
`PERSONALITY_MODES_BRIEF.md` §6.3 had already specified the correct design
(`dog/app/fruitfly_drive.py` bridging straight into the arbiter) a month
earlier.

**Rule:** before building from a diagram or a pasted spec, read the matching
brief in `docs/design/` and grep the code. Where they disagree, the code wins
and the brief is the better guide to intent; a fresh diagram is the weakest
of the three.

### 3. A data pipe is not a feature until something renders it.

The Fruitfly observability work built the whole chain — Python
`/fruitfly/status`, a typed `RobotAdapterPort` method, `BroadcastFruitflyUseCase`,
a STOMP topic — and it was still invisible, because (a) nothing in the console
subscribed to it, and (b) no Java REST route exposed it, so the GUI's own
`hlApi()` call 404'd while the same path worked directly against the adapter
on :15002.

**Rule:** finish a pipe by rendering it, and verify through the transport the
consumer actually uses (via :8080, not the adapter port). "The endpoint
returns data" is not the same as "the feature works".

## Running the stack

### 4. Mode is persisted in Postgres and pushed to the adapter on boot.

Laika came up in **FRUITFLY** on a fresh `docker compose up` — not set by
anyone in that session, but resynced from the previous one. With
`MOCK_MODE` unset, compose defaults `python-bittle-1` to the real robot over
WiFi, so a plain boot can start driving actual hardware with no human in the
loop.

**Rule:** `MOCK_MODE=True docker compose up -d` for any development or demo
work. Shell env beats `.env`, so this needs no file edit. Check the persisted
mode before booting against the real dog.

### 5. Fruitfly's sim is deliberately outside compose — it still needs a route in.

§6.1 keeps `dog/fruitfly/` out of the adapter image (heavy deps, must never
stall motion control), and it talks to the adapter "over plain HTTP on the
same host". But the adapter runs *in a container*, where `127.0.0.1:8765` is
the container's own loopback — so Fruitfly could never reach a host-run sim,
and `fruitfly_drive.py` sat in its "sim unreachable, hold balance" fallback
forever, looking like a bug in the feature.

**Rule:** the compose files now pass
`FRUITFLY_SIM_URL=${FRUITFLY_SIM_URL:-http://host.docker.internal:8765}` with
an `extra_hosts: host-gateway` mapping (needed on Linux). Start the sim with
`python server.py --host 0.0.0.0 --port 8765` — binding loopback-only is not
reachable from the container either. It takes ~40 s to load the matrix.

### 6. Static console assets are baked into the JAR, and the browser caches them.

`src/main/resources/static/*` is packaged at build time, so editing
`cards.js` changes nothing until the orchestrator image is rebuilt — and even
then Chrome serves the cached copy. Several "the fix didn't work" cycles were
only this.

**Rule:** `docker compose up -d --build orchestrator`, then hard-reload
(Ctrl+Shift+R). When a change still seems absent, `curl` the asset off :8080
to see what the server is actually serving before debugging the code.

## Frontend

### 7. FLIP animations must measure layout position, not the rendered rect.

The action cards drifted and floated with uneven gaps. Cause:
`getBoundingClientRect()` returns the **transformed** position, so a
re-render landing mid-animation measured an element that was still sliding
and compounded the offset into the next transform. Entries arrive ~1/s and
the slide runs 0.4 s, so this happened constantly.

**Rule:** measure with `offsetTop` (layout position, ignores transforms) for
both the First and Last reads. Also skip the re-render entirely when nothing
changed — under STOMP the poll was re-animating a stack the stream had
already drawn.

### 8. "It rarely updates" was a granularity problem, not a transport problem.

The card polled every 2 s and still looked dead, because the *content* —
behavior-level run-log rows — only changed when a whole behavior started or
ended, which in Fruitfly is roughly never. Switching to websockets alone
would have changed nothing.

**Rule:** when a live view feels static, check how often the underlying data
can change before reaching for a faster transport. Both were worth doing here
(the feed changes ~1/s, pushed on `/topic/robot/{id}/actions`), but in that
order.

## Tests and CI

### 9. `OpenApiSpecTest` self-heals, and it couples every controller.

Adding a route fails the build once with "regenerated … differs from the
committed copy" — the test **writes** the new `docs/api/openapi.json`, then
asserts the old one matched. Re-running goes green, and the regenerated file
must be committed.

**Consequence worth knowing:** the spec is generated from *all* controllers,
so an uncommitted controller leaves the committed spec describing code that
isn't in the repo, and a clean checkout fails. Commit controllers and the
spec together.

### 10. `RobotControllerTest`'s `@MockitoBean` list tracks the constructor.

`RobotController` is wired by `@WebMvcTest`, so every new `*UseCase`
constructor parameter needs adding to the `@MockitoBean(types = {...})` list
or the context fails to start — an error that reads like a Spring problem,
not a missing-mock problem.

**Related:** use cases themselves need no registration. `ApplicationConfig`'s
`@ComponentScan` picks up anything in `application.usecase` matching
`.*UseCase`, so a new one is a bean the moment it is named correctly.
