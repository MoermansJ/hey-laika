# satellite — Laika's ears, eyes and mood light

A Seeed **XIAO ESP32S3 Sense** rides on Laika's head and talks to the adapter
over its own WiFi. The dog's firmware is untouched (design:
`orchestrator/docs/design/VOICE_RELAY_BRIEF.md` and
`NAVIGATION_MAPPING_BRIEF.md` §Vision satellite).

| Stream | Transport | Consumer |
|---|---|---|
| PDM microphone, 16 kHz mono int16 | UDP to the adapter host, port 5005, 20 ms packets with a 4-byte sequence prefix | `dog/app/ears.py` → whisper → `voice.phrase` events |
| OV2640 camera, QVGA JPEG | HTTP on the XIAO, port 80: `/snap` (one frame), `/stream` (MJPEG), `/` (status JSON) | `dog/app/eyes.py` polls `/snap` → YOLOv8n (onnxruntime) → `vision.person` / `vision.clear` events |
| Grove Chainable RGB LED (P9813), the mood light | HTTP `/led?r=&g=&b=&effect=off\|solid\|pulse\|blink&periodMs=&brightness=` (GET or POST); no query = read back | `dog/app/mood.py` maps framework events to colours; the Eyes tab pins moods by hand |

## Build and flash

```
cp xiao_sense/secrets.h.example xiao_sense/secrets.h   # fill in SSID, password, adapter host
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --board-options "PSRAM=opi,PartitionScheme=default_8MB" satellite/xiao_sense
arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3 --port COMx satellite/xiao_sense
```

`PSRAM=opi` is required: the camera frame buffers live in PSRAM. The
arduino-cli bundled with Arduino IDE 2 works (see
`orchestrator/docs/reports/AUDIT_2026-09-02.md` §10 for its path). Serial is
the USB-CDC port at 115200; the sketch prints WiFi address, mic, camera and
LED state at boot and a packet counter every 10 s.

**If `arduino-cli upload` dies with "No serial data received"** right after
"Stub running..." (it did on 2026-09-03, at 921600 and 115200): the native
USB port re-enumerates when esptool's stub takes over. Flash without the
stub instead, no buttons needed. Export the binaries with
`arduino-cli compile ... --output-dir <dir>` and run esptool from the core:

```
esptool.exe --chip esp32s3 --port COMx --baud 115200 --no-stub write_flash -z \
  --flash_mode dio --flash_freq 80m --flash_size 8MB \
  0x0 <dir>/xiao_sense.ino.bootloader.bin 0x8000 <dir>/xiao_sense.ino.partitions.bin \
  0xe000 <core>/tools/partitions/boot_app0.bin 0x10000 <dir>/xiao_sense.ino.bin
```

(`esptool.exe` lives in `Arduino15/packages/esp32/tools/esptool_py/<ver>/`,
the core in `Arduino15/packages/esp32/hardware/esp32/<ver>/`.) About 35 s.

**Microphone driver:** the sketch uses ESP-IDF's `driver/i2s.h` directly,
not Arduino's `I2S.h` wrapper. With the wrapper active the camera never
delivered a frame (`/snap` → 500) although `esp_camera_init` succeeded;
bisected 2026-09-03 with `-DSATELLITE_MIC=0`. Keep it that way.

## Wiring on the XIAO

| Module | XIAO pins | Notes |
|---|---|---|
| Power | 5V / GND | From analog socket A on the BiBoard (red/black) |
| Chainable RGB LED | **D2 = CI (clock, Grove yellow)**, **D3 = DI (data, Grove white)**, cable in the LED's **IN** port | LED power: **red to the XIAO's 3V3 pin, black to a ground** (the XIAO's GND or any BiBoard socket ground). Not the 5 V socket: the P9813 wants inputs above 0.7 × VDD, which the XIAO's 3.3 V never reaches at 5 V, and the LED then sits pure white ignoring every frame (2026-09-04). The LED's OUT socket is free for a second LED |
| Camera, mic | on-board | Sense expansion board, camera ribbon seated |

## Bench validation (before it goes on the dog)

1. Power from the PC's USB-C. Watch the serial log: `LED: P9813 on D2/D3`,
   `WiFi: <ip>`, `Mic: PDM @16 kHz`, `Camera: OV2640 ready`. The LED blinks
   blue while joining WiFi and goes dark once connected.
2. `GET http://<xiao-ip>/` → status JSON with `"mic":true,"camera":true` and a
   `"led"` object.
3. `GET http://<xiao-ip>/led?r=255&g=0&b=0` → solid red;
   `.../led?r=0&g=0&b=255&effect=pulse&periodMs=1000` → breathing blue.
   Nothing: clock/data swapped, or no power on the LED. Pure white that
   never changes: the LED is on 5 V and cannot read 3.3 V logic, move its
   red wire to the XIAO's 3V3 pin. Wrong colour: P9813 byte order (report it).
4. `GET http://localhost:15001/api/robots/bittle-1/ears` on the adapter →
   `"streaming": true` and `packets` climbing, `dropped` near zero.
5. Say "Hey Laika, sit down" near the board → `ears/transcripts` shows the
   line with `wake: true, intent: sit`; the dog (or Mocha) runs `idle_sit`
   and the LED pulses blue for a moment (`heard`).
6. With `SATELLITE_HOST` set: `GET /api/robots/bittle-1/eyes` →
   `streaming: true`, `fps` ≈ 4; the Eyes tab shows the picture and draws a
   box around you. `http://<xiao-ip>/stream` in a browser is the raw MJPEG.

Tuning knobs at the top of the sketch: `MIC_GAIN_SHIFT` (raise if `ears`
never sees speech, lower if it clips), `FRAME_SIZE`, `JPEG_QUALITY`,
`LED_FRAME_MS` / `LED_CLOCK_US`. On the adapter: `EARS_ENERGY_FLOOR`
(speech gate), `WHISPER_MODEL` (`base` default; `small` is more accurate and
~3× slower on CPU), `EYES_FPS`, `EYES_CONFIDENCE`.

## Power on the dog

Two jumpers from a spare Grove socket's VCC/GND to the XIAO's 5V/GND pins.
Meter the socket first and stream for several minutes while watching the
dog's WebSocket stay up and the battery reading in the Power panel
(WiFi bursts peak ~340 mA; the LED adds up to ~60 mA at full white). A LiPo
on the XIAO's battery pads is the fallback if the rail sags.
