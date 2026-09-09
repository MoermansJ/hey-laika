# Planning Brief — Stationary sensing: measure a lot, walk a little

**Date:** 2026-09-09 · **Status:** planning input (written while the pack charges)
**Builds on:** `NAVIGATION_PHASE1.md` (grid, routes, reactive stop, sweeps),
`../robot/SENSOR_DATA.md` (what each sense yields), `POWER_SAVER_BRIEF.md`
(where the energy goes).

## 1. The premise, checked against the hardware

Walking is the expensive thing: nine servos under load, 13–26 % of the pack
per hour measured, and tonight's pack fell from 39 % to empty in minutes of
light use. Turning in place costs the same legs. Panning the head costs one
servo for a second. Taking a picture costs the satellite's WiFi burst
(~340 mA peak, milliseconds) and the host's CPU, which is free.

Both distance sensors ride the head: the ranger (tonight's sweep readings
changed with the pan angle, so it pans) and the OV2640 on the XIAO. The head
has one axis, pan, −90..90° (joint 0, `m 0 deg`). Standing, a pan therefore
gives a 180° slice of the room at the height of the head for both sensors
at once. Sitting tilts the nose up and rest puts it on the floor, so a scan
is taken standing (`kup`, then `kbalance`), which is also the posture the
navigator leaves her in.

What the dog does today between moves: nothing. The ranger is read at 6 Hz
only while she moves, the camera runs at 4 fps for person detection and is
paused by the battery saver when she is still. The energy-cheap window,
standing still, is the one we do not use.

## 2. The look-around: one stationary scan as the unit of measurement

One `look_around` behavior (a generator, like `sonar_sweep`), from a
standing pose:

1. For each pan angle in −90..90 step 15° (13 stops, or 30° for a quick
   look): pan, settle ~0.4 s, one ranger read, one camera frame at the
   satellite's larger size (VGA, one-off, not the 4 fps stream), both
   stamped with pose, yaw and pan.
2. Return the head to 0. Total ≈ 13 × (0.4 + 0.08 + 0.2) s ≈ 9 s and one
   servo's worth of energy. The legs never move.
3. Everything after that happens on the host (§3), asynchronously; the dog
   is free the moment the head is back.

The ranger gives 13 exact ranges. The camera, with the host's help, turns
each of the 13 frames into many more ranges and into named objects, which
is where the multiplier is.

## 3. Host-side processing of a scan (all offloaded, all optional)

| Step | What it yields | Cost on the PC | Needs |
|---|---|---|---|
| **YOLO, all 80 classes** (today only class 0 is read) | chairs, tables, couches, cats, cups, shoes: named landmarks with a bearing (pan + box centre × half the field of view) | 20–30 ms per frame, already in the image | one line in `eyes.py` |
| **Range for each object** | the ranger reading when the box straddles the beam centre; otherwise a size prior per class (a chair is ~45 cm wide) | none | the camera's horizontal field of view, calibrated once (§6) |
| **Monocular depth, scaled by the ranger** | a relative depth map per frame (Depth Anything small, ONNX, like YOLO today) becomes metric once the pixel under the ranger's beam is pinned to the measured range: hundreds of obstacle points per frame instead of one, at the head's height and below | ~0.3–1 s per VGA frame on CPU, fine for a scan taken once a minute | one model export (`dog/tools/export_depth.py`, same pattern as `export_yolo.py`), and the beam-centre pixel from §6 |
| **Place signature** | a small image embedding per frame; two scans that look alike from the same bearing are the same place. Absolute, like the WiFi fingerprint, but sharper. This is the loop-closure signal Phase 2 wanted | ~10 ms per frame with a MobileNet-class model | one more ONNX file |
| **Floor / not floor** | from the depth map's lower band: is the floor ahead flat and continuous (a step, a cable, a rug edge) | free with the depth map | — |

Outputs feed three layers: the occupancy grid (depth points as rays, the
same `MapBuilder.integrate` path, with a lower confidence step than the
ranger), a new **landmark** table (class, bearing, range, confidence, the
frame it came from, pose at the time), and the **scan bundle** store (§5).

## 4. Choosing where to stand next: information per metre, not coverage per minute

Today `explore` does not exist and routes go where a click says. For
mapping, the host picks the next vantage point:

- Candidates: free cells on the frontier of the known map (free next to
  unknown), plus the current spot with a different heading (a turn in place
  is cheaper than a walk but not free; a re-pan is free and already covered
  the 180° in front, so the only reason to turn is the 180° behind).
- Score = (unknown cells that a 180° look-around from there would see, from
  ray casting on the current grid) ÷ (energy to get there). Energy from the
  action log: metres walked × cost per metre + turns × cost per turn, both
  measured from the pack voltage drop in the log rather than guessed (§5).
- Take the best candidate, walk there (the navigator as it is), look
  around, repeat. Stop when no candidate is worth more than a threshold or
  the saver's eco tier says so. Expect a room to take three to five stops,
  not a stroll.

The same score answers "is a second look-around here worth more than
walking": after a scan the local gain is ~0, so the planner never dithers
in place, and a scan is always taken on arrival because arrival is the
free moment.

## 5. Data gathering for the learning work

One row per scan in a `scans` table: id, time, pose, yaw, battery voltage
before and after, the 13 (pan, range) pairs, the 13 frame paths, and the
derived landmarks and place signatures. Frames go to disk under
`dog/data/scans/<id>/<pan>.jpg` with a size cap (a 300 MB ring is ~10 000
VGA frames, weeks of scans), so the "camera frames not logged" limit of
Phase 1 is lifted where it matters: at the stationary moments, not at 4 fps.

Energy accounting comes from the same pipeline: the action log already
stores the battery before each motion command; adding the voltage after
the command settles (one `P` read, cached) gives cost per command kind and
per metre after a few sessions, which is what §4 divides by. The power
tracker's per-tier drain figures come for free from the same rows.

The ML questions this makes answerable, in order of nearness:

1. Per-surface stride and turn calibration from (command, pose before,
   yaw after, depth-map floor motion) without a tape measure.
2. Object-class range priors from (box size, ranger range) pairs.
3. Place recognition from signatures; drift correction when a scan matches
   an old one (the pose-graph relaxation of the navigation brief).
4. Cost of a room: which vantage points paid off, for the §4 planner.

## 6. One-off calibrations (need the dog, ten minutes, no walking)

- **Field of view**: a ruler at 1 m in front of the camera, one frame:
  degrees per pixel. Expect ~65° horizontal for the OV2640.
- **Beam-centre pixel**: a small object at 50 cm, pan until the ranger
  reads it; the box centre in that frame is where the ranger points.
- **Head geometry**: neck pivot to ranger and to lens, in cm, for the ray
  origin (`sensorOffsetM` in the map builder, plus the pan pivot).
- **Pan settle time**: the shortest settle at which the ranger reading no
  longer changes after a 15° step.

## 7. Firmware wish, queued not required

A `sweep` token that pans and reads the ranger in one firmware pass and
returns the 13 numbers in one reply would halve the scan time and take the
pans off the WebSocket. The look-around works without it; it goes on
`FIRMWARE_QUEUE.md` for the next flash.

## 8. Phasing

- **A. Look-around behavior + scan bundles** (adapter): pan, range, VGA
  frame, storage with the ring cap, `POST /navigation/look`, scan rows in
  `/navigation/scans`, the Map tab shows the 13 rays and thumbnails. All
  mock-testable (the mock world can render nothing, so frames come from a
  fixture set). One session.
- **B. Landmarks**: all-class YOLO, bearing and range per object, the
  landmark table, dots with labels on the map. One session.
- **C. Metric depth**: model export, scale by the ranger, depth points
  into the grid and the floor check. One to two sessions; the first live
  check is whether the depth map's scale holds across a room.
- **D. Vantage planner + energy model**: the §4 score, the after-voltage
  in the action log, `explore` as an arbiter behavior at the idle-plus
  priority the navigation brief reserved. One session.
- **E. Place signatures and drift correction.** After C, when there are
  scans to match.

Order of live checks once she is charged: §6 calibrations first (standing
only, cheapest), then a single look-around, then the Phase 1 runbook's
walking steps, since each of those now ends with a free scan.

## 9. Open questions

1. Frame size for scans: VGA (640×480, ~25 KB) or the sensor's SXGA for
   detail at the cost of a slower snapshot? Lean VGA.
2. Depth model: Depth Anything V2 small versus MiDaS small; pick by CPU
   time at 320 px on this PC, measured in Phase C's first hour.
3. Disk cap for frames and where it lives (the adapter's `/data` volume in
   compose is the natural place).
4. ~~Does the sitting posture tilt the head too far for a useful scan?~~
   Answered 2026-09-09 (owner): sitting pitches the head about 45° up.
   The ranger then climbs a metre per metre of range and the camera's
   lower edge sits ~20° above horizontal, so no floor or furniture is in
   view. Scans are taken standing. A sitting frame is a ceiling view,
   static and distinctive per room; kept in mind as an extra place
   signature if wall views ever prove ambiguous, not planned.
