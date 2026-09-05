# hey-laika 🐕

An AI companion robot built around **Laika**, a Petoi Bittle X V2 robot dog
driven over WiFi. A Java orchestrator runs her personality loop and web
console, a Python adapter owns the hardware, and a XIAO ESP32S3 Sense on her
head gives her ears, eyes and a mood light. The decision engine is a local
Ollama model by default; Claude is opt-in.

This is a personal project for exactly one dog. There is no genericity for a
hypothetical second robot, and the docs say so wherever it matters.

## What she does today

- **Personality loop** — the orchestrator decides actions from a six-dimension
  personality model and drives the dog through the adapter's `/execute_action`.
- **Behavior framework** — one motion arbiter, stored behaviors, event
  bindings, boot greeting, idle ladder, and provenance for every motion.
- **Voice** — "Hey Laika" wake phrase: the satellite mic streams PCM over UDP,
  faster-whisper transcribes on the host, an LLM answers, and the reply plays
  on a Grove Speaker Plus wired to the BiBoard.
- **Eyes** — the satellite camera feeds a YOLOv8n ONNX person detector;
  presence and absence become framework events.
- **Mood light** — a chainable RGB LED on the satellite mapped to framework
  events, with named moods and a host-stepped rainbow.
- **Proximity leash** — WiFi RSSI to a phone hotspot or home beacon, zones,
  labelled marks, a dead-man stop.
- **Senses and map** — WiFi fingerprint sniffing, ultrasonic ranging, and a
  dead-reckoned pose with calibrated stride and turn constants.
- **Web console** — dashboard, control panel with live servo writes, sequence
  builder, Mind, Audio input, Audio output, Vision, Leash, Map and Metrics
  tabs, pushed over STOMP.
- **Gait learner** — supervised stride/turn calibration sessions.

## Hardware

| Part | Role |
|---|---|
| Petoi Bittle X V2 with BiBoard V1.0 (ESP32) | The dog. Driven over its own WiFi WebSocket; USB serial also works |
| Seeed XIAO ESP32S3 Sense | The satellite on her head: PDM mic, OV2640 camera, own WiFi |
| Grove Chainable RGB LED (P9813) | Mood light, hung off the satellite |
| Grove Speaker Plus | Her mouth, on GPIO 10 of the BiBoard's Grove UART socket |
| Grove Ultrasonic Ranger | Distance sensing, on GPIO 9 of the same socket |

Laika runs a fork of the OpenCat ESP32 firmware. The fork adds WiFi-slot
tools, a 1 Hz RSSI event, a second SSID slot and the dead-man. Its source is
not part of this repository (`opencat-esp32/` is gitignored as a third-party
clone); what is flashed and why is recorded in
[`orchestrator/docs/design/FIRMWARE_RESET.md`](orchestrator/docs/design/FIRMWARE_RESET.md)
and queued changes in
[`FIRMWARE_QUEUE.md`](orchestrator/docs/design/FIRMWARE_QUEUE.md). The
adapter's WiFi transport speaks the stock firmware's WebSocket protocol, so
basic control works without the fork; the leash and senses features need it.

## Repository layout

| Directory | What |
|---|---|
| [`orchestrator/`](orchestrator/) | Java 21 / Spring Boot 3.5 fleet orchestrator, clean architecture enforced by ArchUnit, the web console, `docker-compose.yml` for the whole stack, and the project docs in [`orchestrator/docs/`](orchestrator/docs/) |
| [`dog/`](dog/) | Python 3.11 / Flask adapter for one robot: mock, serial and WiFi transports, the arbiter and behavior store, ears, mouth, eyes, mood, leash, senses, power tracking, gait learner |
| [`satellite/`](satellite/) | Arduino sketch for the XIAO ESP32S3 Sense: mic over UDP, camera and LED over HTTP |
| `.github/workflows/` | CI: the orchestrator's `mvnw test` and the adapter's `pytest` on every push |

`petoi/`, `opencat-esp32/` and `noncodefiles/` are gitignored on purpose:
third-party reference clones used for protocol mining, and local scratch.

## Quick start

Docker is the only prerequisite. Nothing needs an API key.

```bash
cd orchestrator
cp .env.example .env
# no robot? set MOCK_MODE=True in .env
# have one?  set BITTLE_WIFI_HOST to the BiBoard's LAN address
docker compose up --build
docker compose exec ollama ollama pull llama3.2:1b   # once; the default model
# console at http://localhost:8080
```

The stack is PostgreSQL, Ollama, the adapter for Laika on host port 15001,
a second adapter on 15002 running "Mocha", a rich mock robot used as a GUI
fixture, and the orchestrator on 8080. Everything in `.env` is documented
inline in [`orchestrator/.env.example`](orchestrator/.env.example) and
[`dog/.env.example`](dog/.env.example).

To use Claude as the decision engine instead of Ollama, set
`DECISION_ENGINE=claude` and `ANTHROPIC_API_KEY` in `.env`. The key reaches
the adapter containers only; the orchestrator never sees it.

### With the satellite

Copy `satellite/xiao_sense/secrets.h.example` to `secrets.h`, fill in the
WiFi credentials and the adapter host, build and flash as described in
[`satellite/README.md`](satellite/README.md), then set `SATELLITE_HOST` in
`.env`. The eyes also need the ONNX weights, exported once with
`dog/tools/export_yolo.py`.

## No authentication, by design

There is no authentication anywhere in this stack. The orchestrator's REST
API, the adapter's routes (including raw commands and servo writes), the
STOMP endpoint, the satellite's HTTP server and Postgres all accept any
caller. The stack is built for one owner on a trusted home LAN. **Never
port-forward, tunnel or bind any of these ports on an untrusted network.**
If that ever changes, add authentication first. The reasoning is recorded in
[`orchestrator/docs/reports/AUDIT_2026-09-02.md`](orchestrator/docs/reports/AUDIT_2026-09-02.md).

## Development

```bash
# orchestrator: unit tests, a @WebMvcTest slice and the ArchUnit rules;
# no database or adapter needed
cd orchestrator && ./mvnw test

# adapter: tests force MOCK_MODE and the mock decision engine
cd dog && pip install -r requirements-dev.txt && pytest -q
```

Each directory's README covers its own run modes, configuration and full
route table. Architecture for the orchestrator is in
[`orchestrator/docs/design/ARCHITECTURE.md`](orchestrator/docs/design/ARCHITECTURE.md).

## Documentation

Start at [`orchestrator/docs/README.md`](orchestrator/docs/README.md), which
indexes every file:

- `robot/` — the dog itself: hardware, firmware capabilities, network
  protocol, sensor catalogue, validation captures
- `design/` — architecture and feature briefs: behavior framework, leash,
  navigation, voice relay, observability, firmware reset and queue
- `reports/` — dated status reports, audits and calibration sessions
- `archive/` — superseded documents kept for history

## History

The `orchestrator` and `dog` repositories were merged into this monorepo on
2026-08-31 with both histories intact. The satellite was added on 2026-09-02.
