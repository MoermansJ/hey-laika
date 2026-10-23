# `dog/reconstruction/` — Fly View room reconstruction

A monocular depth map of whatever Laika is looking at, turned into a
coloured point cloud for the Fly View demo. Design doc:
[Fly View: Live Room Reconstruction](https://claude.ai/artifact/YQCvvN8v9qf2AoVLLPbm5C),
brief: [`orchestrator/docs/design/FLY_VIEW_BRIEF.md`](../../orchestrator/docs/design/FLY_VIEW_BRIEF.md).

**This is not part of the adapter.** It is its own process with its own
environment, like `dog/fruitfly/`, for two reasons that are not negotiable
on this hardware:

- the PC's GPU is an AMD RX 5700 XT, so inference goes through DirectML,
  and Docker Desktop on Windows cannot pass an AMD GPU into a container;
- `onnxruntime-directml` and the adapter's CPU `onnxruntime` share an
  import name, so one environment cannot hold both.

## Install and run

```bash
python -m venv dog/reconstruction/.venv
dog/reconstruction/.venv/Scripts/pip install -r dog/reconstruction/requirements.txt
dog/reconstruction/.venv/Scripts/python dog/tools/download_depth_model.py --model small small-fp16   # ~145 MB

# one saved frame -> a PLY and a depth preview
dog/reconstruction/.venv/Scripts/python dog/tools/depth_to_cloud.py --fixture person --preview

# one live frame, pulled through the adapter's cache
dog/reconstruction/.venv/Scripts/python dog/tools/depth_to_cloud.py --from-url http://localhost:8080

# the gate
dog/reconstruction/.venv/Scripts/python dog/reconstruction/validate.py --offline
```

## The contract

| Piece | In | Out |
| --- | --- | --- |
| `depth.DepthAnythingOnnx.infer(jpeg)` | JPEG bytes | `(disparity HxW float32, rgb HxWx3 uint8)`, disparity larger = nearer, arbitrary units |
| `cloud.to_points(disparity, rgb, settings)` | the above + settings | `(xyz Nx3 float32 metres, rgb Nx3 uint8, stats)` in the camera frame: +x right, +y up, +z forward, origin at the lens |
| `cloud.to_binary_frame(xyz, rgb)` | a cloud | the viewer's wire format: `FLYC` magic, uint32 count, uint32 stride (15), uint32 reserved, then 12 B of float32 xyz + 3 B of rgb per point |
| `cloud.write_ply(path, xyz, rgb)` | a cloud | binary little-endian PLY, opens in any mesh viewer |
| `frames.FrameSource.fetch(fresh)` | base URL + robot id | one JPEG from `GET /api/robots/<id>/eyes/snap?fresh=1`, or `FrameError` |

Frames always come from the adapter's cache, never from the XIAO
directly: `dog/app/eyes.py` already polls `/snap` and caches the newest
frame, and the satellite serves one camera and one microphone off one
small radio.

## The service

```bash
dog/reconstruction/.venv/Scripts/python dog/reconstruction/server.py     --port 8766 --source adapter --base-url http://localhost:8080
```

Host process, port 8766 (fruitfly's sim sits on 8765). `--source fixture`
(the default) runs the whole pipeline with the dog switched off.

| Route | Returns |
| --- | --- |
| `GET /health` | `{ok, model, provider, providerLoaded, weights, source, uptimeS}` |
| `GET /state` | settings, whether a cloud is held, its point count, the last capture's stats, the last error, the frame source's status |
| `GET /settings` · `POST /settings` | the settings map; a POST merges, clamps and always answers 200 with the notes |
| `POST /capture` | one frame to one cloud: `{at, source, frameBytes, frameSize, provider, inferenceMs, totalMs, cloud:{...}}`, or 502 when the frame cannot be fetched, 503 when the weights are missing |
| `GET /cloud` | the newest cloud as a binary PLY attachment, 404 before the first capture |
| `GET /cloud/stats` | the last capture's numbers without the payload |

## Settings

Defaults and clamps live in `settings.py`; `resolve()` never raises, it
clamps and reports, so a slider dragged to an absurd place mid-demo cannot
take the service down.

| Setting | Default | What it does |
| --- | --- | --- |
| `source` | `fixture` | `fixture` needs no dog; `adapter` pulls a live frame. A setting, not a launch flag, so the demo can switch mid-run |
| `frameBaseUrl` | `http://localhost:8080` | the orchestrator (or `:15001` for the adapter directly); the PC's Tailscale address in the split demo setup |
| `robotId` | `bittle-1` | which robot's `/eyes/snap` to pull |
| `model` | `small` | which ONNX file: `small`, `small-fp16`, `base`, `base-fp16` |
| `confidenceCutoff` | 0.05 | drops the farthest slice of the depth range; the model has no confidence channel, so this stands in for one |
| `edgeReject` | 0.10 | drops pixels on a depth cliff, where a depth map bleeds one surface into another |
| `pointDensity` | 20000 | points kept after thinning; QVGA is 76,800 |
| `hfovDeg` | 65.0 | OV2640 horizontal field of view, **uncalibrated** (STATIONARY_SENSING_BRIEF.md §6 has the ruler procedure) |
| `nearM` / `farM` | 0.4 / 6.0 | placeholder scale: monocular depth has no true scale. Phase 5 replaces this with the ranger and the occupancy grid |
| `captureIntervalS` | 0.0 | 0 = manual capture only. Above 0 it arms a background loop; the button is the demo's trigger, so this stays off by default |

## Validation

`validate.py` runs every step for real — weights, both providers, the DPT
preprocessing rule, depth on a photograph and on known room geometry, the
cloud, the settings clamps, the PLY, the wire format, and the capture path
against a stub adapter. An unvalidated step fails the run; there is no
"skipped" outcome. `--offline` drops the steps that need Laika powered on
and names them in the summary every time.

It deliberately does not live in `dog/tests`: the adapter's pytest suite
and CI must not depend on this venv, these weights, or a GPU.
