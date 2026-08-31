# Docs

Three sections:

## `robot/` — the dog itself (reference, kept current)

Hardware, firmware, and protocol documentation for the physical Bittle X.
These are living reference docs — update them when facts change.

- [HARDWARE.md](robot/HARDWARE.md) — board, battery, servo map, transports, care notes
- [FIRMWARE_CAPABILITIES.md](robot/FIRMWARE_CAPABILITIES.md) — full catalog of what the stock firmware can do
- [NETWORK_API.md](robot/NETWORK_API.md) — the board's live network surface (WebSocket protocol, ports)
- [VALIDATION_RESULTS.md](robot/VALIDATION_RESULTS.md) — raw live captures that validated the serial protocol

## `design/` — feature designs and specs

What we intend to build and how. May drift from implementation; the code wins.

- [PERSONALITY_SYSTEM_DESIGN.md](design/PERSONALITY_SYSTEM_DESIGN.md) — v1.1 personality/behavior architecture
- [BITTLE_ENHANCED_GUI_SPEC.md](design/BITTLE_ENHANCED_GUI_SPEC.md) — dashboard/GUI spec
- [WEBSOCKET_REAL_TIME_GUIDE.md](design/WEBSOCKET_REAL_TIME_GUIDE.md) — dashboard real-time (STOMP) design

## `reports/` — point-in-time status reports and reviews

Snapshots of project state at a date. Historical record — superseded claims
get dated addenda, not rewrites.

- [SERVO_POC_STATUS_REPORT.md](reports/SERVO_POC_STATUS_REPORT.md) — 2026-08-30 full-stack assessment (see its addendum)
- [SERVO_POC_VALIDATION_PLAN_REVIEW.md](reports/SERVO_POC_VALIDATION_PLAN_REVIEW.md) / [SERVO_POC_VALIDATION_SUITE_REVIEW_2.md](reports/SERVO_POC_VALIDATION_SUITE_REVIEW_2.md) — validation-plan reviews
- [SPATIAL_MVP_REVIEW.md](reports/SPATIAL_MVP_REVIEW.md) — 2026-08-31 spatial exploration MVP preparation findings
