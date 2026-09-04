# Docs

Four sections. Every file under `docs/` has one line here; keep it that way.

## `robot/` — the dog itself (reference, kept current)

Hardware, firmware, and protocol documentation for the physical Bittle X.
These are living reference docs — update them when facts change.

- [HARDWARE.md](robot/HARDWARE.md) — board, battery, servo map, transports, care notes; firmware row states what is actually flashed (hey-laika fork, base B10_251121)
- [FIRMWARE_CAPABILITIES.md](robot/FIRMWARE_CAPABILITIES.md) — full catalog of what the stock firmware can do
- [NETWORK_API.md](robot/NETWORK_API.md) — the board's live network surface (WebSocket protocol, ports)
- [SENSOR_DATA.md](robot/SENSOR_DATA.md) — 2026-09-03 catalogue of every sense on Laika: fields, rates, events, what is stored, and what the hardware produces that nothing reads yet
- [VALIDATION_RESULTS.md](robot/VALIDATION_RESULTS.md) — raw live captures that validated the serial protocol
- [calibration_backup_2026-09-01.txt](robot/calibration_backup_2026-09-01.txt) — raw `?`/`c` dump of Laika's servo calibration and board banner, taken before the fork was flashed

## `design/` — architecture, feature designs and planning briefs

What we intend to build and how. May drift from implementation; the code wins,
except for `ARCHITECTURE.md`, which is the authoritative description of the
Java orchestrator's structure.

- [ARCHITECTURE.md](design/ARCHITECTURE.md) — orchestrator clean architecture: layers, package map, use-case convention, behavior loop, broadcasting, persistence, testing conventions
- [FIRMWARE_RESET.md](design/FIRMWARE_RESET.md) — the "CSS reset" cut list for the BiBoard firmware; status line records which cuts are flashed on the hey-laika fork
- [PERSONALITY_SYSTEM_DESIGN.md](design/PERSONALITY_SYSTEM_DESIGN.md) — v1.1 personality/behavior architecture (Phase 1b done; dated status notes mark what is still deprecated-but-present)
- [BEHAVIOR_FRAMEWORK_BRIEF.md](design/BEHAVIOR_FRAMEWORK_BRIEF.md) — 2026-08-31 brief: one arbitrated behavior framework (stored behaviors, bindings, arbiter, provenance)
- [PROXIMITY_LEASH_BRIEF.md](design/PROXIMITY_LEASH_BRIEF.md) — 2026-09-01 brief: phone-tethered leash via WiFi RSSI, marks, dead-man
- [NAVIGATION_MAPPING_BRIEF.md](design/NAVIGATION_MAPPING_BRIEF.md) — 2026-09-01 brief: perceptual mapping from WiFi fingerprints + sonar, rooms, `goto_room`
- [OBSERVABILITY_MIND_BRIEF.md](design/OBSERVABILITY_MIND_BRIEF.md) — 2026-09-01 brief: request metrics page and the per-robot Mind tab
- [VOICE_RELAY_BRIEF.md](design/VOICE_RELAY_BRIEF.md) — 2026-09-01 brief: XIAO ESP32S3 Sense mic → host transcription → decision layer; Grove Speaker Plus output
- [ARRIVAL_DAY_RUNBOOK.md](design/ARRIVAL_DAY_RUNBOOK.md) — 2026-09-03 checklist for the XIAO Sense, Speaker Plus and ultrasonic ranger: pin validation order, bench tests, power check
- [FIRMWARE_QUEUE.md](design/FIRMWARE_QUEUE.md) — changes pooled for the next BiBoard / satellite flash, with their bench checks; flashing is a ritual, so it happens in batches

## `reports/` — point-in-time status reports and reviews

Snapshots of project state at a date. Historical record — superseded claims
get dated addenda, not rewrites.

- [AUDIT_2026-09-02.md](reports/AUDIT_2026-09-02.md) — 2026-09-02 whole-project audit (orchestrator, adapter, firmware fork, GUI, docs) with prioritised fixes and feature speculation
- [CALIBRATION_2026-08-31.md](reports/CALIBRATION_2026-08-31.md) — 2026-08-31 dead-reckoning calibration session on the gym-mat grid (raw runs, derived stride/turn constants)
- [PLANNER_HANDOFF_CALIBRATION.md](reports/PLANNER_HANDOFF_CALIBRATION.md) — self-contained handoff from the calibration session for planning waypoint mapping
- [SERVO_POC_STATUS_REPORT.md](reports/SERVO_POC_STATUS_REPORT.md) — 2026-08-30 full-stack assessment (see its addendum)
- [SERVO_POC_VALIDATION_PLAN_REVIEW.md](reports/SERVO_POC_VALIDATION_PLAN_REVIEW.md) / [SERVO_POC_VALIDATION_SUITE_REVIEW_2.md](reports/SERVO_POC_VALIDATION_SUITE_REVIEW_2.md) — validation-plan reviews
- [SPATIAL_MVP_REVIEW.md](reports/SPATIAL_MVP_REVIEW.md) — 2026-08-31 spatial exploration MVP preparation findings (2026-09-02 addendum: the leash verdict is superseded)

## `archive/` — superseded documents, kept for history

Each file carries an "Archived" banner naming its successor. Nothing here
matches the code any more; do not build from these.

- [FIRMWARE_COMPLETE_SUMMARY.md](archive/FIRMWARE_COMPLETE_SUMMARY.md) — pre-fork firmware roadmap overview → superseded by `design/FIRMWARE_RESET.md`
- [FIRMWARE_IMPLEMENTATION_RUNBOOK.md](archive/FIRMWARE_IMPLEMENTATION_RUNBOOK.md) — day-by-day runbook for that roadmap → superseded by `design/FIRMWARE_RESET.md`
- [FIRMWARE_WEB_CONFIG.md](archive/FIRMWARE_WEB_CONFIG.md) — on-board web configuration system (`/api/config/*`, never built) → superseded by `design/FIRMWARE_RESET.md`
- [FIRMWARE_AUDIO_ALERTS.md](archive/FIRMWARE_AUDIO_ALERTS.md) — MAX98357A/INMP441 audio stack (dropped) → superseded by `design/VOICE_RELAY_BRIEF.md`
- [BITTLE_ENHANCED_GUI_SPEC.md](archive/BITTLE_ENHANCED_GUI_SPEC.md) — early fleet-console GUI spec → superseded by `design/ARCHITECTURE.md`
- [WEBSOCKET_REAL_TIME_GUIDE.md](archive/WEBSOCKET_REAL_TIME_GUIDE.md) — bidirectional STOMP topic scheme (the current layer is push-only) → superseded by `design/ARCHITECTURE.md`
