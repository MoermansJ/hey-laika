# BITTLE AI COMPANION - ACTIVE CONTEXT

Phase: 1b+ (real hardware, WiFi transport, orchestrator-owned behavior loop)
Status: Robot drives live over WiFi; full stack containerized
Updated: 2026-09-02

Current state:
- Hardware validated live: Bittle X (Laika). Firmware is the hey-laika fork
  (reset Phase A cuts 1/3/4, partial 2/6, plus XW tools, event_rssi, second
  SSID, dead-man) built with the version date pinned, so it still reports
  B10_251121 — see orchestrator/docs/design/FIRMWARE_RESET.md. Serial
  protocol (115200, echo-on-completion, binary I frames) captured in
  orchestrator/docs/robot/VALIDATION_RESULTS.md; servo API + /execute_action
  shipped
- Robot provisioned onto home WiFi (auto-reconnects each boot; IP is
  DHCP-assigned — see BITTLE_WIFI_HOST in .env, reserve it on the router).
  WiFiBittleController speaks the firmware's WebSocket protocol
  (ws://<ip>:81, JSON task frames, b64: binary) and is validated driving the
  robot. Serial remains supported for USB-tethered use
- docker compose (in ../orchestrator) runs the whole stack — postgres, ollama,
  this adapter (WiFi hardware mode by default), the "Mocha" rich-mock adapter
  (GUI fixture), orchestrator — no native process needed
- Behavior framework Phase 1: single motion arbiter, stored behaviors,
  bindings, greeting + idle ladder, leash watchdog, senses/WiFi sniffer,
  power tracker, adaptive polling
- Voice MVP ("Hey Laika"): text-in via Ollama llama3.2:1b, buzzer feedback;
  XIAO ESP32S3 Sense mic + Grove Speaker Plus ordered
  (orchestrator/docs/design/VOICE_RELAY_BRIEF.md)
- Decision engine: **Ollama by default** (DECISION_ENGINE=ollama, local,
  zero cost); Claude is opt-in (DECISION_ENGINE=claude + ANTHROPIC_API_KEY,
  model claude-opus-5); mock available for tests. Personality system v1.1
  Phase 1b done: the orchestrator's loop drives /execute_action. The
  adapter's own /personality, /behavior, /autonomous/*, /interact/* routes
  are deprecated and still present
- Deviations from BITTLE_PROJECT_SETUP.md: modern dependency versions
  (anthropic>=0.116, not 0.7.0); adapters/repositories/services dirs deferred

Next:
- Work the prioritised fix list in
  orchestrator/docs/reports/AUDIT_2026-09-02.md §8 (adapter items: WS
  retry-while-busy, idle-ladder timing, DEBUG default + bind address,
  arbiter-owned motion, SQLite WAL, deprecated-brain removal, tests)
- Voice hardware when it arrives (VOICE_RELAY_BRIEF.md build plan)
- Navigation per orchestrator/docs/design/NAVIGATION_MAPPING_BRIEF.md
