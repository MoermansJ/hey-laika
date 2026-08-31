# BITTLE AI COMPANION - ACTIVE CONTEXT

Phase: 1+ (real hardware, WiFi transport)
Status: Robot drives live over WiFi; full stack containerized
Updated: 2026-08-31

Current state:
- Hardware validated live: Bittle X, firmware B10_251121. Serial protocol
  (115200, echo-on-completion, binary I frames) captured in
  orchestrator/docs/VALIDATION_RESULTS.md; servo API + /execute_action shipped
- Robot provisioned onto home WiFi (auto-reconnects each boot; IP is
  DHCP-assigned — see BITTLE_WIFI_HOST in .env, reserve it on the router).
  WiFiBittleController rewritten to the stock firmware's WebSocket protocol
  (ws://<ip>:81, JSON task frames, b64: binary) and validated driving the
  robot. Serial remains supported for USB-tethered use
- docker compose (in ../orchestrator) runs the whole stack — postgres, ollama,
  this adapter (WiFi hardware mode by default), orchestrator — no native
  process needed now that no COM port is involved
- Voice MVP ("Hey Laika"): text-in via Ollama llama3.2:1b, buzzer feedback;
  mic/speaker hardware pending
- Decision engine: mock (no ANTHROPIC_API_KEY yet); personality system v1.1
  Phase 1 done
- Deviations from BITTLE_PROJECT_SETUP.md: modern dependency versions
  (anthropic>=0.116, not 0.7.0); adapters/repositories/services dirs deferred

Next session:
- Personality Phase 1b (adapter endpoint) and Phase 2 (Claude director);
  needs ANTHROPIC_API_KEY
- Voice hardware (mic/speaker) when it arrives; swap Ollama model up
- Spatial exploration MVP per orchestrator/docs/SPATIAL_MVP_REVIEW.md
