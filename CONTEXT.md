# BITTLE AI COMPANION - ACTIVE CONTEXT

Phase: 0
Status: Foundation scaffolded
Updated: 2026-08-27

Current state:
- Full Phase 0 codebase generated (Flask app, personality engine, choreography,
  mock/serial/wifi controllers, SQLAlchemy models, dashboard + display UI,
  Dockerfile + docker-compose, tests)
- Anthropic SDK integration targets current API (model: claude-opus-5, with
  server-side refusal fallback); mock decision engine runs when no API key set
- Deviations from BITTLE_PROJECT_SETUP.md: modern dependency versions
  (anthropic>=0.116, not 0.7.0); adapters/repositories/services dirs deferred
  (controller classes cover Phase 0); project rooted directly in F:\projects\dog

Next session:
- Verify docker-compose up after Docker Desktop install completes (reboot pending)
- Add ANTHROPIC_API_KEY to .env to enable Claude decisions
- Phase 1: assemble Bittle, switch BITTLE_COMMUNICATION_METHOD=serial
