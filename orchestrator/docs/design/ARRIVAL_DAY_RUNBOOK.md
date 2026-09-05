# Arrival-day runbook — XIAO Sense, Speaker Plus, ultrasonic ranger

**Date written:** 2026-09-02 (hardware due 2026-09-03) · **Owner:** Jonathan
**Prepared software (all committed, tested without the hardware):**
satellite sketch (`satellite/xiao_sense`), adapter ears (`dog/app/ears.py`),
mouth (`dog/app/mouth.py`), ultrasonic read (`/senses/range`), firmware speaker
playback (`opencat-esp32/src/speaker.h`, needs one more flash of Laika).

The order below follows the briefs: the ultrasonic pin is validated first
because it decides which UART-socket wire the speaker gets.

## 0. Before opening the box (10 min)

- [ ] Router: reserve a DHCP address for the XIAO (like Laika's 192.168.0.246).
- [ ] `satellite/xiao_sense/secrets.h`: SSID, password, `ADAPTER_HOST` = this PC's
      LAN address (the compose file publishes `5005/udp` from the adapter).
- [ ] Flash Laika with the speaker-enabled fork (same ritual as 2026-09-02:
      hold BOOT, tap Reset, release; `esptool --before no_reset`; recipe in
      `reports/AUDIT_2026-09-02.md` §10). Banner must still read `hey-laika-A2`.
- [ ] Stack up: `docker compose up -d --build` (adapter image now carries
      faster-whisper and espeak-ng). `GET /api/health` → healthy.
- [ ] Multimeter ready. Tape ready.

## 1. Ultrasonic ranger — decides the UART-socket pins (15 min)

**Done 2026-09-03:** ranger answers on **GPIO 9** (pin 10 silent); 0 misses in 120 stationary reads. `ULTRASONIC_PIN=9`, so the speaker wire is GPIO 10. Detail in `NAVIGATION_MAPPING_BRIEF.md` addendum.

Wiring per NAVIGATION_MAPPING_BRIEF §4: UART socket female conversion cable,
**yellow→ranger SIG**, red+black→ranger power. Note whether yellow is GPIO 9 or 10
on this cable (BiBoard V1 UART socket: RX 9, TX 10).

1. Dog on, resting. `Xs` is not needed: all firmware modules are off since
   2026-09-02, so nothing else drives those pins.
2. Hand in front of the ranger, then:
   ```
   curl "http://localhost:15001/api/robots/bittle-1/senses/range?pin=9"
   curl "http://localhost:15001/api/robots/bittle-1/senses/range?pin=10"
   ```
   The pin that answers `"ok": true` with a sane `distanceCm` is the ranger.
   Move the hand: the number must follow.
3. Put that pin in `orchestrator/.env` as `ULTRASONIC_PIN=`; the other one is
   `SPEAKER_PIN=`. `docker compose up -d python-bittle-1` to apply.

## 2. Speaker Plus — the dog's mouth (15 min)

Wiring: **white→speaker SIG** on the UART socket (the pin left over from
step 1), red+black→speaker power from the I2C socket (power tap only).
Volume pot on the Speaker Plus at a quarter turn to start.

1. `GET /api/robots/bittle-1/mouth` → `enabled: true`, `pin` correct.
2. Playback path without any TTS engine:
   ```
   curl -F "file=@dog/tests/fixtures/hey_laika_sit.wav" http://localhost:15001/api/robots/bittle-1/mouth/wav
   ```
   Expect intelligible walkie-talkie speech. If it buzzes at a constant tone:
   wrong pin (the firmware answered `XWp` but the wire goes elsewhere). If
   silent: check the speaker's power tap and pot.
3. TTS: Voice tab → Mouth → "Speak". Inside Docker espeak-ng answers; with
   `ELEVENLABS_API_KEY` set the Eleven Labs voice is used instead.
4. Firmware serial log during playback should stay quiet; the ISR runs at
   8 kHz. If a gait stutters while speaking, note it — pacing knobs are
   `CHUNK_BYTES` in `mouth.py` and the ring size in `speaker.h`.

## 3. XIAO Sense on the bench (20 min)

1. USB-C to the PC. Flash:
   ```
   arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --board-options "PSRAM=opi,PartitionScheme=default_8MB" satellite/xiao_sense
   arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3 --port COMx satellite/xiao_sense
   ```
   (Sketch already compiles: 22 % flash.)
2. Serial 115200: `WiFi: <ip>`, `Mic: PDM @16 kHz`, `Camera: OV2640 ready`.
3. `GET http://<xiao-ip>/` → status JSON; `http://<xiao-ip>/stream` in a browser.
4. Adapter: `GET /api/robots/bittle-1/ears` → `streaming: true`, `packets`
   climbing, `dropped` ≈ 0. Voice tab → Ears card shows the same.
5. Say "Hey Laika, sit down" at arm's length. First utterance loads whisper
   (~15 s once), then transcripts appear within ~2 s. Expect `wake: true,
   intent: sit` and Laika sits (binding `voice.phrase` → `idle_sit`).
   - Nothing heard: watch `GET /ears` → `level` while speaking; `peak`
     must clear `floor` (fan noise idles at ~50 rms, ~160 peak). Lower
     `EARS_ENERGY_FLOOR` in `.env` or raise `MIC_GAIN_SHIFT` in the sketch.
   - Heard but no wake: read the transcript text; add the spelling whisper
     used to `WAKE_VARIANTS` in `ears.py`.
6. Say "Hey Laika, lie down" and "Hey Laika, hello" to exercise `rest` and
   `greet`.

## 4. XIAO on the dog (20 min)

Wiring per the brief: analog socket A female cable, **red+black→XIAO 5V/GND**.
No data wires.

1. Multimeter on the socket: expect ~5 V under load.
2. Mount the XIAO on the head (camera forward; the sketch flips the image,
   change `set_vflip`/`set_hmirror` if it is mounted the other way).
3. Stream for five minutes: `/stream` open in a browser, ears `streaming: true`,
   and the dog's `GET /api/health` staying healthy. Watch the Power panel's
   battery reading; a sag of more than a few percent in five minutes means
   the rail is marginal — LiPo on the XIAO's battery pads is the fallback.
4. Walk test: `kwkF` for ten seconds while streaming; both streams must
   survive the servo load.

## 4b. Mood light and eyes (added 2026-09-03, LED and camera wired)

Software: satellite `/led` (P9813 driver, D2 clock / D3 data), adapter
`mood.py` + `eyes.py` (YOLOv8n through onnxruntime), orchestrator relays,
the **Eyes** tab. One-time on the PC: `dog/tools/export_yolo.py` (already
run; `dog/models/yolov8n.onnx` is gitignored, re-run after a fresh clone).

**Done 2026-09-03 (evening):** flashed over the XIAO's own USB-C on COM4 with
the no-stub esptool recipe (`satellite/README.md`; `arduino-cli upload`
dies at the stub handover). XIAO is **192.168.0.189**. Camera and mic only
worked together after the mic moved to ESP-IDF `driver/i2s.h`. Pillow was
missing from the image (added). `SATELLITE_HOST` set, adapter and
orchestrator containers rebuilt. LED and the on-dog stream not yet seen:
the dog was off (LED power comes from analog socket B).

1. `.env`: `SATELLITE_HOST=<xiao-ip>` (both `orchestrator/.env` for compose
   and `dog/.env` for a native run). `docker compose up -d --build
   python-bittle-1 orchestrator` (new Python modules, new Java relays).
2. Flash the updated sketch (same build line as §3). Boot: the LED blinks
   **blue while joining WiFi**, then goes dark (the adapter owns it now).
   Serial prints `LED: P9813 on D2/D3` and `HTTP: / /snap /stream /led`.
   - Never lights: swap the yellow/white wires (clock and data crossed), then
     check the LED's power (red on the XIAO 3V3 pin, black on GND).
   - Pure white, never changes: the LED is on the 5 V socket. The P9813
     needs inputs above 0.7 × VDD and the XIAO drives 3.3 V, so at 5 V no
     frame is ever accepted. Move red to the XIAO's 3V3 pin (2026-09-04).
   - Wrong colours: `GET http://<xiao-ip>/led?r=255&g=0&b=0` must be red;
     if it is blue the P9813 byte order is off (report it, don't guess).
3. `GET /api/robots/bittle-1/mood` → `enabled: true`, `sets` ≥ 1 within
   30 s (the resync loop paints the base mood). Eyes tab → Mood light card:
   click **happy** (green), **lost** (red blink); the colour picker pins any
   colour. Say "Hey Laika, sit" → the LED pulses blue for 2.5 s (`heard`),
   then returns. Speak from the Mouth card → teal pulse while it talks.
4. `GET /api/robots/bittle-1/eyes` → `streaming: true`, `fps` ≈ 4,
   `detector.loaded: true` after the first frame (first inference ~1 s).
   Eyes tab → Camera card shows the picture at ~3 fps with green boxes on
   people; the chip says `1 in view · left/centre/right`.
   - `detector.available: false`: run `dog/tools/export_yolo.py`.
   - `lastError` mentions `/snap`: the satellite is up but the camera is not
     (`camera: false` in `/satellite`) — reseat the camera ribbon.
5. Walk in front of the dog: `vision.person` events appear in the Behavior
   Lab run log only if you enable the seeded (disabled) binding; the mood
   light shows cyan (`person`) on its own. Step out of view: `vision.clear`
   after 2 s and the LED returns to the base mood.

## 4c. Speaker firmware flash and first sound (2026-09-04, night)

Outcome: the speaker fork (`XWp/XWa/XWq`) is on Laika and a bark clip
played through the Grove Speaker Plus from the Control tab; six 1 KB frames
acknowledged, ring buffer draining at 8 kHz. Three things cost the evening
and are worth knowing:

- **Laika was not on WiFi after the flash.** The esp-wifi primary slot held
  the *iPhone hotspot*, not the router (a leash walk's WiFi-manager join had
  overwritten it), so both slots failed with reason 201 "no AP found". Fix
  applied: router stored in the fork's secondary slot (`XW2%SSID%pass` over
  serial), primary since cleared by the BOOT-hold countdown. Boot now spends
  ~25 s failing the (absent) hotspot before joining the router. Proper fix
  pending: an `XW1` tool to write the primary, since the stock `w%` command
  is intercepted by the loop's BOOT check on this board.
- **The 2.4 KB audio frame crashed the firmware** (LoadProhibited in
  `startWebTask`: a String whose allocation failed has a NULL buffer and
  `strcpy(NULL+1)` follows). Adapter now sends 1024-byte chunks (works);
  firmware commit `a51fd08` drops such commands instead of crashing and is
  **built but not yet flashed** (`scratchpad fw/fix`, rebuild from the fork).
- **Flashing this BiBoard.** The CH343's DTR line drives the BOOT pin (the
  firmware prints "reboot and use Wifi manager" whenever the PC asserts
  DTR, and holding it >2 s clears the primary WiFi slot); RTS does **not**
  reach EN, so no PC-side sequence can enter download mode and a software
  restart keeps the previously latched strapping value. Download mode needs
  a **hardware** reset with BOOT low: hold BOOT, tap Reset, release, then
  `esptool --before no_reset`. It took several tries tonight; a power-on
  with BOOT held (battery off, USB replug) is the fallback. Open the serial
  console with DTR and RTS released or the firmware reboots.
- The startup greeting stood the dog up on the desk on reconnect and it
  fell. Greeting disabled (`POST /greeting/disable`) for bench work; the
  dog now sits on a stable low platform. Re-enable when it is on the floor.

## 4d. What the "bark" actually was (2026-09-04, next morning)

The clip was heard as a series of loud electric ticks, not a bark, and the
mood light was stuck pure white all evening. Both are explained:

- **Speaker.** GPIO 10 is TX2 of the Grove serial module, which the stock
  V1.0 table enables by default and protects from `Xs`. `printToAllPorts`
  writes every response line to it at 115200 baud, so each acknowledged
  frame's `=` reply went into the amplifier as one tick: six frames, six
  ticks. Fix queued in `FIRMWARE_QUEUE.md` rows 3 and 4 (module off, `XWp`
  ends `Serial2`, IRAM-safe ISR), built as the 2026-09-04 batch.
- **LED.** P9813 input threshold is 0.7 × VDD. On the 5 V socket that is
  3.5 V; the XIAO drives 3.3 V, so no frame was ever accepted and the
  driver stayed in its power-on state with all three sinks on: white. The
  satellite reported every request as applied because its side is fine.
  Fix: power the LED from the XIAO's 3V3 pin (wiring only, no flash).
  Verified without the dog's help by querying the satellite directly: it
  accepted red at brightness 40 and a blue pulse; the LED stayed white.

Afternoon and evening, same day, how it actually ended:

- The 3.3 V feed alone changed the LED from white to blue; it still accepted
  nothing. The LED started working once its cable and the XIAO pins were
  re-checked wire by wire (IN port, yellow D2, white D3, red 3V3, black to
  a ground). Verify with the satellite's `/led` read-back *and* your eyes.
- The speaker's yellow had been on the XIAO's **D2**, the LED clock line:
  every LED frame was a 50 kHz burst into the amplifier. After moving it to
  a BiBoard socket it was on an analog socket first (silence) and finally
  on the UART socket's white lead (GPIO 10). The socket was identified by
  moving the ranger's yellow onto the same cable's yellow lead and reading
  a distance. Batch 2 (LEDC PWM) then produced tones, and batch 3 (4 KB
  prebuffer, `XWf`) continuous speech. 1536-byte audio frames stall the
  firmware's WebSocket layer until a reboot: keep 1024.
- esptool's closing "hard reset via RTS" does nothing on this board; after
  every flash tap Reset by hand or the dog stays in the flasher stub.
- Describe wiring to the owner as *cable and colour to labelled pin*, one
  complete picture at a time. Socket numbers and "third pin down" cost an
  hour.

## 5. Record the outcome

Add a dated addendum to `VOICE_RELAY_BRIEF.md` and `NAVIGATION_MAPPING_BRIEF.md`
with: the ranger pin, the speaker pin, mic gain, whether the rail held, first
transcript latency. Commit `.env`-free config changes (`.env` stays local).

## Not prepared (next sessions)

- Host-side YOLO consumer for `/stream` → `vision.person` events, follow-me.
- End-of-utterance VAD (energy gate is the v1).
- openWakeWord as a cheaper first gate in front of whisper.
