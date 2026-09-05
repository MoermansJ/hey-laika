# Laika's sensor data — what can be read today, and what is left on the table

**Updated:** 2026-09-05 (ears `level`, DC-offset gate fix) · Reference for the perception work (one snapshot
of the world for the GUI and the agent). Every sense listed here is
installed and wired; "exposed" means it is readable from the adapter API
right now, "stored" means it lands in `bittle.db`, "dormant" means the
hardware produces it but nothing reads it yet. Field names are the JSON
keys as served by the adapter (`/api/robots/bittle-1/...`) and relayed
unchanged by the orchestrator.

## At a glance

| Sense | Where it lives | Rate today | Exposed at | Events |
|---|---|---|---|---|
| Camera (OV2640, QVGA) | XIAO satellite, head | 4 fps polled by the adapter | `/eyes`, `/eyes/snap` | `vision.person`, `vision.clear` |
| Microphone (PDM) | XIAO satellite, head | 16 kHz continuous, UDP | `/ears`, `/ears/transcripts` | `voice.phrase` |
| Ultrasonic ranger | UART socket, GPIO 9 | on demand, ≤ 1 read / 150 ms | `/senses/range` | none yet |
| IMU (ICM42670) | BiBoard | yaw read once per sniff; exceptions pushed | inside `/senses/samples`; `exception.report` | `exception.report` |
| Battery (`P`) | BiBoard | every 10 s (adaptive up to 40 s idle) | `/status`, `/power` | `battery.low` |
| WiFi RSSI to the router | BiBoard (`event_rssi`) | 1 Hz push while the leash is on | `/leash` | `leash.near/warn/far/lost` |
| WiFi fingerprint scans | BiBoard (`XWs`) | one scan per quiet minute, ~2 s blocking | `/senses`, `/senses/samples` | none yet |
| Dead-reckoned pose | adapter (from commands) | per bounded move | `/senses`, `/senses/samples` | none yet |
| Servo positions | BiBoard (`j`) | on demand | `/servo` | none |
| Satellite health | XIAO status JSON | on demand (Vision tab every 15 s) | `/satellite` | none |
| Mood light (actuator, but stateful) | XIAO, D2/D3 | on change, resync every 30 s | `/mood` | consumes events |
| Speaker (actuator) | UART socket, GPIO 10 | on demand | `/mouth` | none |
| Bittle X voice module | BiBoard Serial1 | pushes `X…` lines when it hears its phrases | dormant | none |
| Back-touch pad (`XB`) | BiBoard, if fitted | firmware push | dormant, module off since 2026-09-02 | none |

## Camera — `/eyes`

Source: the XIAO's `/snap`, one JPEG per poll, 320×240, ~5–6 KB indoors.
The adapter caches the latest frame and serves it at `/eyes/snap` so any
number of browser tabs cost the XIAO nothing extra. Detection runs on the
host: YOLOv8-nano, ONNX, 320 px input, ~20–30 ms per frame on this PC.

| Field | Meaning |
|---|---|
| `streaming`, `fps`, `targetFps`, `frames`, `lastFrameAgeS` | pipeline health; `fps` is measured over the last 5 s |
| `persons[]` → `x, y, w, h, confidence` | boxes normalised 0..1 to the frame (top-left origin), persons only, NMS applied |
| `personCount`, `lastPersonAgeS` | how many now, how long since anyone |
| `inferenceMs` | last detector run |
| `detector` → `model, available, loaded, confidence, inputSize` | model file present / warmed up |
| `personEvents`, `clearEvents`, `errors`, `lastError` | counters |

Event payload (`vision.person`, ≤ 1/s while someone is in view): the
largest box plus `count`, `offset` (box centre vs frame centre, −1 far
left .. +1 far right, the follow-me steering signal) and `area` (fraction of
the frame, a crude distance proxy). `vision.clear` once, 2 s after the last
sighting, with `lastSeenS`.

Stored: nothing. Frames are not kept; detections live only in the status.

**Left on the table**

- The model already scores all 80 COCO classes; only class 0 (person) is
  read. Cats, dogs, chairs, cups, phones, bottles are one line away.
- Frame statistics that need no model: mean brightness (room lit or dark,
  lens covered), sharpness (moving vs still), frame-to-frame difference
  (motion in view while nobody is detected).
- Face-level detail (who it is, where they look) would need a second model.
- The XIAO can change exposure, gain, white balance and resolution through
  the sensor API; none of it is exposed. VGA at 2–3 fps is available for
  snapshots that deserve detail.
- Timestamps are adapter-side. The XIAO does not stamp frames.

## Microphone — `/ears`

Source: 16 kHz mono int16 PCM in 20 ms UDP packets with a sequence number,
gain ×8 on the XIAO. The adapter gates speech on RMS energy, cuts
utterances (0.4–8 s, 0.8 s of silence ends one), transcribes with
faster-whisper `base` on CPU, and gates on the wake phrase.

| Field | Meaning |
|---|---|
| `streaming`, `packets`, `dropped`, `lastSeq`, `lastPacketAgeS` | transport health; `dropped` from sequence gaps |
| `utterances`, `wakes`, `lastText`, `lastError` | pipeline counters |
| `model`, `modelLoaded`, `wakePhrase`, `udpPort`, `sampleRate` | configuration |
| `level` → `rms, peak, median, floor, speaking` | live loudness: DC-free RMS of the last 20 ms packet, peak and median over the last second, the gate floor (`EARS_ENERGY_FLOOR`), and whether the gate is open |
| `vocabulary` → `phrases, variants, builtinVariants, prompt` | the custom vocabulary (`/ears/vocabulary`): phrases whisper is primed with, extra accepted spellings of the name, and the effective prompt |

`/ears/transcripts`: every utterance whisper turned into text, wake or not:
`at, text, wake, intent, durationS, latencyS`. Stored in `transcripts`,
last 500 rows kept.

The Audio input tab polls `/ears` and the transcripts once a second, and
its phrase recorder (`POST /ears/record`) captures the microphone for a
few seconds regardless of the gate and prints what whisper heard, so a
mis-spelling of the name can be adopted into the vocabulary on the spot.
On the mood light a wake is steady green and a wake that carried the
greet intent pulses green; the console's badges take their colours from
the same table (`/mood` → `palette`, `badges`).

Event payload (`voice.phrase`, only after the wake phrase): `text`,
`command` (the part after the wake phrase), `intent` (`sit, rest, stand,
come, stop, greet, unknown`), `transcriptId`.

**Left on the table**

- Sound level beyond `level`: a longer noise-floor estimate, dBFS, and a
  history for the Ears card's meter. Note the PDM mic carries a DC offset
  of ~1700 after the ×8 gain; until 2026-09-05 the gate measured that
  offset instead of the sound and stayed open permanently (8 s blocks,
  all discarded by whisper's VAD). The RMS is mean-subtracted now.
- Non-speech sounds: a loud bang, a doorbell, clapping, the dog's own
  buzzer. The energy gate already sees them; whisper returns nothing.
  An onset detector or a small sound-classifier (YAMNet-class) would turn
  them into events.
- Utterances that did not start with the wake phrase are transcribed and
  stored but never become events: "things said near the dog" is a data
  set that already exists in the table.
- Whisper can return per-segment confidence and language; not surfaced.
- Speaker identity (owner vs stranger) would need an embedding model.
- No direction of arrival: one microphone.

## Ultrasonic ranger — `/senses/range`

Source: firmware `XU` one-shot read on GPIO 9, trigger and echo on the same
pin; ~50–90 ms round trip over WiFi, the adapter caps it at one read per
150 ms and keeps the last 60. `-1` from the firmware (no echo inside the
~2 m window) is `null` here.

| Field | Meaning |
|---|---|
| `distanceCm`, `ok`, `pin`, `at`, `readMs`, `cached` | this reading |
| `recent[]` | last 60 readings of the configured pin, `null` = miss |
| `reads`, `misses`, `lastReadMs` | counters since start |

Validated 2026-09-03: 0 misses in 120 reads on a stationary target; misses
come in bursts on moving targets; anything inside the beam (a leg, the
floor when the head tilts) wins over the wall behind it, so treat the
number as "nearest thing ahead".

Stored: nothing. Events: none.

**Left on the table**

- Nothing polls it when the Vision tab is closed. A background sampler at
  2–5 Hz would give a continuous trend (closing speed, cm/s) and the
  `nav.blocked` / `person.approaching` events the navigation brief wants.
- Range + head pan (joint 0, −90..90°) = a cheap sweep: a polar occupancy
  slice ahead of the dog, the `sonar_sweep` step type in the brief.
- Range + camera box `area` = a calibration of "how far is a person of
  this apparent size", which then works when the ranger is looking elsewhere.
- Miss-rate over time is itself a signal (a moving target in front).

## IMU — inside `/senses/samples`, plus `exception.report`

Source: ICM42670 on the BiBoard. The firmware streams full 6-axis data on
request (`gP`: accel x/y/z and yaw/pitch/roll) and answers a single `gp`
read; it also pushes exception lines on its own: fall over, knocked,
pushed (with direction and force angle), free fall, lifted, dropped,
off-direction auto-correct, `endTurn`.

Exposed today: `yaw` on every fingerprint sample (the `gp` read is taken at
sniff time), and the exception events as `exception.report` with `code`
(matched against bindings, e.g. `flipped`). Stored: `yaw` per sample.

**Left on the table**

- Pitch and roll are read and discarded. They tell whether the dog is on a
  slope, tipping, or being carried at an angle.
- Continuous yaw is not read between sniffs, so the pose still dead-reckons
  turns from commands (`driftM` grows). One `gp` per bounded move would fuse
  it; the brief calls this "IMU feedback inside the odometry shadow".
- Accelerometer magnitude over time = activity level, gait vibration,
  whether it is being petted/lifted, whether a step actually happened.
- The push events already distinguish pushed-from-which-direction and
  the force angle; only the code reaches the framework, the direction
  and angle are dropped in `handle_output_line`.
- `gc` calibration state and the balance gains are readable (`g?`).

## Battery and power — `/status`, `/power`

Source: firmware `P` (voltage), converted to a percentage on the 2S LiPo
curve (full ≈ 8.35 V, floor ≈ 6.8 V). Polled every 10 s, stretched to 40 s
when the dog is resting. The power tracker opens a session at power-on and
closes it at power-off.

| Field | Meaning |
|---|---|
| `battery` (percent), `signal` | live, on `/status` |
| `connected`, `state`, `unreachableSince` | reachability |
| `avgDrainPctPerHour`, `predictedMinutesLeft` | from the session history |
| `sessions[]` → `startedAt, startBattery, endedAt, endBattery, durationS, drainPctPerHour` | stored |

Also copied onto every fingerprint sample (`battery`).

**Left on the table**

- Raw voltage is not exposed, only the percentage; the sag under load
  (walking vs resting) is a health signal on its own.
- Drain per activity (walking minutes vs idle) would need the arbiter's run
  log joined to the session; both tables exist.

## WiFi — `/leash`, `/senses`

Two different things share the radio:

**RSSI to the router** (`event_rssi`, 1 Hz push from the firmware while the
leash is enabled): `rssi` (EMA-smoothed), `rssiRaw`, `ssid`, `zone`
(`near, warn, far, lost` with hysteresis and dwell), `frameAgeS`, the
thresholds in `config`, and the labelled `marks` recorded on walk tests.
Events: `leash.<zone>` on every transition, payload `zone, previous, rssi`.

**Fingerprint scans** (`XWs`, blocking ~2 s, only in motion gaps, at most
once a minute, suppressed in away mode): every visible access point as
`ssid, bssid, rssi, channel`, with the pose the dog thought it had
(`x, y, heading, driftM`), `battery`, `yaw`, `source` (`auto` sniffer or
`manual` button), and `t`. Stored in `wifi_samples`, unlimited; the Map
tab filters by time, source, minimum AP count, and thinning.

**Left on the table**

- Localisation itself: k-NN over stored fingerprints to name the room. The
  brief's phase 3; all the data is there.
- RSSI to the *phone* (the "come to me" search) needs the BLE path from the
  leash brief; the firmware can report it but nothing asks.
- The satellite has its own RSSI (`/satellite` → `rssi`), a second radio at
  head height. Two RSSIs to the same router from two antennas a few cm apart
  is a modest but free diversity signal.

## Pose — `/senses`

Dead reckoning from the bounded-motion vocabulary: commanded turns update
`heading`, bounded advances update `x, y` by a calibrated stride
(`strideMPerCycle`, 0.10 m default, tape-measure later). `driftM` grows
with every move and a restart adds a penalty; `POST /senses/pose/reset`
re-anchors. Honest, coarse, and the only position estimate the dog has.

## Servos — `/servo`

`j` readback returns the 16 commanded angles (joint 0 head pan, 8–15 hips
and knees; 1–7 are placeholders on Bittle). These are targets, not measured
positions: the stock servos have no feedback. Reading posture ("is it
sitting") means comparing the vector against the known skill poses.

**Left on the table**

- Current posture as a named state is inferred nowhere; the idle ladder
  and the arbiter know what they commanded, not what the body is doing.
- `fp` could read true angles *if* feedback servos were fitted (unverified).

## Satellite health — `/satellite`

The XIAO's own status: `mic`, `camera`, `packets` (audio packets sent),
`rssi`, `uptimeS`, `adapter` (where it streams audio), `led` (what it is
showing, and `sets`). Free heap and the LED name print on its serial line
every 10 s but are not in the JSON.

## Dormant hardware

- **Bittle X voice module** (Serial1): recognises its own fixed phrases and
  up to 10 trained ones offline and emits `X…` codes; the firmware passes
  them through. Nothing on the host binds them; the satellite mic + whisper
  replaced it as the trigger. Still the only *offline* wake path.
- **Back-touch pad** (`XB`, four zones): the firmware pushes petting events
  if the pad is fitted and the module enabled; all modules were switched off
  in the 2026-09-02 reset. If the pad is present, this is free affection
  data.
- **RGB eyes on the ultrasonic module**: the Petoi ranger variant carries
  LEDs driven by `C r g b idx effect`; the Grove ranger fitted here has
  none.

## What is stored, in one list

`transcripts` (every utterance), `wifi_samples` (every sniff with pose,
battery, yaw), `power_sessions`, `framework_behavior_runs` (every behavior
run with its cause: the event and payload that triggered it),
`behavior_logs` and `interactions` (the activity feed and agent decisions),
`conversation_messages`, `metrics_counters`. Camera frames, ranger readings,
RSSI series, and IMU streams are **not** stored; they exist only as the
latest value. A perception snapshot that logs all of them at 2 Hz for a
rolling window is the missing piece for prediction, see
`../design/NAVIGATION_MAPPING_BRIEF.md` addenda and the "World" proposal.
