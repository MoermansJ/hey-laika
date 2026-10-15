---
name: run-stack
description: Launch and drive the hey-laika stack (orchestrator, adapters, console) and the Fruitfly connectome sim. Use when asked to run, start, boot, demo or screenshot the app, or to confirm a change works in the real console rather than only in tests.
---

# Running hey-laika

The verified path, including the parts that cost time to rediscover. Docker
is the only prerequisite; nothing here needs an API key.

## Before anything: do not drive the real dog

```bash
cd orchestrator && MOCK_MODE=True docker compose up -d
```

`MOCK_MODE=True` is **not optional** for development. Compose defaults
`python-bittle-1` ("Laika") to the real robot over WiFi, and the orchestrator
pushes the *persisted* mode from Postgres to the adapter on boot — so a plain
`up` can immediately start driving real hardware. Shell env overrides `.env`,
so this needs no file edit.

Prefer **`bittle-2` ("Mocha")** for all demos: it is hardcoded in compose as a
pure mock with a simulated room, so it is safe regardless of `.env`.

If Docker Desktop is not running, the daemon error is
`npipe:////./pipe/dockerDesktopLinuxEngine ... cannot find the file`. Start
Docker Desktop and wait for `docker info` to succeed before retrying.

## Wait for health, then drive it

```bash
docker compose ps                                        # all should be healthy
until curl -sf http://localhost:8080/personality.html >/dev/null; do sleep 2; done
```

Console at `http://localhost:8080`. Adapters are on :15001 (Laika) and
:15002 (Mocha) for talking to the Python side directly.

Useful probes (through the orchestrator, which is what the console uses —
a path can work on :15002 and still 404 on :8080 if no Java route exists):

```bash
curl -s localhost:8080/api/robots/bittle-2/mode
curl -s -X POST localhost:8080/api/robots/bittle-2/mode/fruitfly
curl -s localhost:8080/api/robots/bittle-2/arbiter/status
curl -s "localhost:8080/api/robots/bittle-2/actions/feed?limit=10"
```

## Changing the console (static assets)

`orchestrator/src/main/resources/static/*` is packaged into the JAR, so edits
are invisible until the image is rebuilt — and then the browser still serves
its cached copy:

```bash
MOCK_MODE=True docker compose up -d --build orchestrator
```

Then hard-reload the page (Ctrl+Shift+R). If a change still seems missing,
`curl http://localhost:8080/cards.js | grep ...` to see what the server is
actually serving before debugging the code.

## The Fruitfly connectome sim

It is deliberately a separate process, outside compose (heavy deps, and a slow
sim must never stall motion control). Without it, Fruitfly mode runs its
"sim unreachable, hold balance" fallback and the console shows
`HOLD (sim unreachable)` instead of decoded directions.

```bash
cd dog/fruitfly && ../.venv/Scripts/python.exe server.py --host 0.0.0.0 --port 8765 --hz 8 --quiet
```

- **`--host 0.0.0.0` matters**: bound to loopback it is unreachable from the
  adapter container. Compose passes
  `FRUITFLY_SIM_URL=http://host.docker.internal:8765` with an `extra_hosts`
  host-gateway mapping.
- It takes ~40 s to load the 165k-neuron matrix before it answers. Poll
  `curl -s localhost:8765/command` until it responds rather than sleeping.
- The cached matrix lives in the gitignored `dog/fruitfly/data/` (~1.1 GB).
  If it is missing, `download.py` needs `NEUPRINT_TOKEN` — a human step.

## Watching a mode actually generate actions

Stationary is correctly idle: nothing drives her, and the idle ladder is
disabled, so an empty queue there is not a bug. Fruitfly is the reliable
demo — one continuous generator, bursting about once a second:

```bash
curl -s -X POST localhost:8080/api/robots/bittle-2/mode/fruitfly
curl -s "localhost:8080/api/robots/bittle-2/actions/feed?limit=10"
```

To fill the arbiter's pending queue (which stays empty in Fruitfly/Roaming,
since those are single generators), submit several *distinct* behaviors fast —
duplicate names are rejected, so reuse of one name will not stack:

```bash
for b in idle_sit idle_rest rest_now startup_greeting acknowledgment power_nap; do
  curl -s -X POST localhost:8080/api/robots/bittle-2/arbiter/invoke \
    -H "Content-Type: application/json" -d "{\"behavior\":\"$b\"}" >/dev/null
done
```

## Leave it as you found it

Put both robots back to `stationary` when finished, and stop the sim process.
A mode left persisted in Postgres is what the next boot will push to the
adapter — including to the real robot.
