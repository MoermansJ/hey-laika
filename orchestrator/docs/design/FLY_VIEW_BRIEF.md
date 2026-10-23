# Planning Brief — Fly View: live room reconstruction

**Date:** 2026-10-23 · **Status:** phase 1 in progress (AGENT-20..25)
**Design doc:** [Fly View: Live Room Reconstruction](https://claude.ai/artifact/YQCvvN8v9qf2AoVLLPbm5C) — Jon's decisions and the agent log live there
**Builds on:** `STATIONARY_SENSING_BRIEF.md` (host-side depth from a standing
pose, the camera calibrations), `NAVIGATION_PHASE1.md` (the occupancy grid
this must not duplicate), `../robot/SENSOR_DATA.md`

## 1. What it is

For the Laika presentation: a third-person view of a fruit-fly avatar
standing inside a 3D reconstruction of the real room, built from the
Bittle's camera. One photo gets you a lumpy room; more photos and the
ultrasonic ranger sculpt it.

## 2. Architecture, as decided after the repo audit

```
XIAO (/snap, QVGA JPEG)  ->  adapter eyes.py (polls, caches)
                                   |  GET /api/robots/<id>/eyes/snap?fresh=1
                                   v
            reconstruction sidecar (HOST process, own port, dog/reconstruction/)
                                   |  binary Float32 cloud over its own websocket
                                   v
                          three.js viewer (served by the sidecar)

orchestrator  ->  toggle, settings, state over STOMP /topic (never cloud data)
```

Four corrections the audit forced on the original sketch, all of them
load-bearing:

- **Host-native, not in the adapter image.** The PC's GPU is an AMD RX 5700
  XT: no CUDA, and Docker Desktop on Windows cannot pass an AMD GPU into a
  container. Inference goes through DirectML on the host, with a CPU
  fallback. `dog/fruitfly/` is the precedent for a sidecar with heavy deps.
- **Frames are pulled, not streamed, and never from the XIAO directly.**
  `eyes.py` already polls `/snap` and caches the newest frame; a second
  poller would contend with the camera the microphone shares a radio with.
- **Cloud data never travels over STOMP.** QVGA is 76,800 points. The
  viewer takes a binary Float32 frame from the sidecar's own socket;
  `/topic` carries toggle, settings and state only.
- **The occupancy grid stays the source of truth** for walls and scale
  (`dog/app/occupancy.py`, fed by `map_builder.py`). The cloud is the
  detail layer, rescaled to the grid in phase 5. There is no second room
  model.

## 3. Deployment for the demo

The orchestrator runs on Jon's laptop; this service runs on the PC and is
reached over Tailscale. The laptop pulls a frame from the dog and forwards
it; the viewer page is served from the PC's Tailscale address. Tailscale
round-trip gets measured before the demo depends on it (AGENT-26), and a
recorded fallback stands by (AGENT-31).

## 4. Phases and tickets

| Phase | Ticket | Done when |
| --- | --- | --- |
| 1a — depth proof | AGENT-20 | a saved frame produces a room-shaped cloud, gate green |
| 1b — sidecar skeleton | AGENT-21 | every endpoint answers with stubbed data |
| 1b — frame source | AGENT-22 | `POST /capture` pulls through the adapter's cache |
| 1b — depth to cloud + settings | AGENT-23 | point count tracks the density budget |
| 1b — viewer + fly | AGENT-24 | capture puts a cloud on screen with the fly in it |
| 1 — validation gate | AGENT-25 | every step invoked; a skip fails the run |
| 2 — live path over Tailscale | AGENT-26 | a live frame becomes a cloud in a couple of seconds |
| 3 — viewer polish | AGENT-27 | watchable without explanation |
| 4 — accumulation | AGENT-28 | the room improves across standing captures; reset clears it |
| 5 — scale from the grid | AGENT-29 | measured distances agree within tolerance |
| 6 — orchestrator + tuning panel | AGENT-30 | end to end, no manual script launching |
| — recorded fallback | AGENT-31 | plays back with the dog switched off |
| — look-around stimulus | AGENT-32 | the connectome question answered or the fallback chosen |
| — visual odometry | AGENT-33 | a walked sequence fuses without smearing |

## 5. Behaviour rules

- **Laika stays autonomous.** The reconstruction never commands her to
  move. The capture button *nudges* the fly brain toward a stationary
  look-around; the fly brain decides how. Fallback if the connectome has
  no such input: `map_builder.sweep()`'s head pan (AGENT-32).
- **Capture is manual.** One frame per button press. The loop interval is
  an optional setting, off by default.
- **Fuse only from standing poses.** Dead reckoning drifts with every move
  and there is no yaw feedback in the loop, so walking fusion waits for
  visual odometry (AGENT-33).

## 6. Scale, honestly

Monocular depth has no true scale. Phase 1 maps relative disparity onto a
`nearM`..`farM` placeholder, which makes the cloud room-*shaped*, not
room-*sized*. Phase 5 fixes it the way `STATIONARY_SENSING_BRIEF.md` §3
already proposed: pin the pixel under the ranger's beam to the measured
range, then scale the cloud and snap it to the grid. The camera's field of
view (`hfovDeg`, default 65°) is still uncalibrated — §6 of that brief has
the ten-minute ruler procedure.

## 7. Contracts for a Java reader

Every Python piece has a named contract and a repeatable validation script;
see [`dog/reconstruction/README.md`](../../../dog/reconstruction/README.md)
for the function-level table, the settings and the wire format. The gate is
`dog/reconstruction/validate.py`, which fails rather than skips.
