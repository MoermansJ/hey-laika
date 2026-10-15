# hey-laika — working notes for Claude

An AI companion robot built around **Laika**, a Petoi Bittle X V2. A Java
orchestrator runs the fleet console and personality modes, a Python adapter
owns the hardware, a XIAO ESP32S3 satellite gives her ears/eyes/mood light.
One dog, not a product — there is no genericity for a hypothetical second
robot, and the docs say so wherever it matters.

`orchestrator/` Java 21 / Spring Boot 3.5 · `dog/` Python 3.11 / Flask ·
`satellite/` Arduino · `dog/fruitfly/` the connectome sim (own process).
`petoi/`, `opencat-esp32/`, `noncodefiles/` are gitignored third-party/scratch.

## Commands

```bash
cd dog && ./.venv/Scripts/python.exe -m pytest tests     # adapter suite
cd orchestrator && ./mvnw -o test                        # orchestrator suite
cd orchestrator && MOCK_MODE=True docker compose up -d   # the whole stack
```

To run or drive the stack, use the **`run-stack` skill** in
`.claude/skills/run-stack/` — it has the verified path, including the parts
that are easy to get wrong.

## Hazards

- **`MOCK_MODE=True` before any `docker compose up`.** Compose defaults
  `python-bittle-1` to the real robot over WiFi, and the orchestrator pushes
  the *persisted* mode to the adapter on boot — so a plain `up` can start
  driving real hardware with no human in the loop. Shell env beats `.env`, so
  no file edit is needed.
- **Static console assets are baked into the JAR.** Editing
  `orchestrator/src/main/resources/static/*` changes nothing until that image
  is rebuilt, and the browser then serves the cached copy. Rebuild the
  orchestrator, hard-reload, and `curl` the asset off :8080 if in doubt.
- **Never commit secrets.** Keys live in gitignored `.env` only; the
  orchestrator never sees the Anthropic key, only the adapter containers do.

## Conventions that will bite if ignored

- **The arbiter (`dog/app/arbiter.py`) owns all motion.** Everything submits
  through it with a `cause`; priority ladder is safety > manual > agent >
  lifecycle > idle. Nothing dispatches to firmware around it.
- **The arbiter queue is behavior-grained, not action-grained.** Roaming and
  Fruitfly each submit ONE long-running generator, so per-decision detail
  (FORWARD, a route leg) lives in `dog/app/action_feed.py`, not in `queued`
  or the run log. A generator names its decision with `step["label"]`.
- **Use cases self-register.** Anything in `application.usecase` named
  `*UseCase` becomes a bean via `ApplicationConfig`'s ComponentScan — no
  wiring needed. But `RobotControllerTest`'s `@MockitoBean(types = {...})`
  list must gain every new constructor parameter or the context won't start.
- **`OpenApiSpecTest` self-heals.** Adding a route fails the build once while
  it rewrites `docs/api/openapi.json`; re-run to go green and commit the
  regenerated spec alongside the controller.
- **Every file under `docs/` gets one line in `docs/README.md`.**
- Commits are Conventional Commits (`feat(scope): …`).

## Where the truth lives

Check these before building from a diagram or a pasted spec — twice now, a
doc has described Java components that do not and should not exist:

- `orchestrator/docs/design/ARCHITECTURE.md` — authoritative for the Java side
- `orchestrator/docs/design/PERSONALITY_MODES_BRIEF.md` — the four modes,
  Fruitfly's design, phase status
- `orchestrator/docs/design/LESSONS.md` — traps already hit, with the rules
  that came out of them. Read it before a long debugging detour.
- `orchestrator/docs/README.md` — index of every doc

Where a brief and the code disagree, the code wins and the brief is the
better guide to intent. A fresh diagram is the weakest of the three.
