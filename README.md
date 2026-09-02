# hey-laika 🐕

AI companion robot project built around **Laika**, a Petoi Bittle X V2 robot
dog driven over WiFi. LLM-driven personality (local Ollama by default, Claude
opt-in), fleet orchestration, live servo control, a proximity leash, voice
interaction, and dead-reckoning navigation experiments.

## Layout

| Directory | What |
|---|---|
| [`orchestrator/`](orchestrator/) | Java Spring Boot fleet orchestrator + web GUI (dashboard, control panel, sequence builder) and the project docs (`orchestrator/docs/`) |
| [`dog/`](dog/) | Python Flask adapter for one robot: hardware transports (WiFi WebSocket / USB serial / mock), behavior framework, ears (whisper) and mouth (speaker), gait learning |
| [`satellite/`](satellite/) | XIAO ESP32S3 Sense sketch: Laika's microphone and camera, streaming to the adapter over its own WiFi |

Two sibling directories are gitignored on purpose: `petoi/` and
`opencat-esp32/` are third-party reference clones (Petoi desktop app and the
BiBoard firmware source) used for protocol mining.

## Quick start

```bash
cd orchestrator
cp .env.example .env      # set BITTLE_WIFI_HOST to your robot's IP
docker compose up --build
# dashboard at http://localhost:8080
```

By default the stack drives real hardware over WiFi; set `MOCK_MODE=True`
in `orchestrator/.env` to simulate without a robot.

## Documentation

Start at [`orchestrator/docs/README.md`](orchestrator/docs/README.md):
`robot/` (hardware, firmware capabilities, network API), `design/` (feature
designs), `reports/` (dated status reports, calibration sessions).

## History

This monorepo absorbed the previously separate `orchestrator` and `dog`
repositories on 2026-08-31; both full histories are merged in.
