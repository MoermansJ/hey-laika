# satellite — Laika's ears and eyes

A Seeed **XIAO ESP32S3 Sense** rides on Laika's head and streams to the adapter
over its own WiFi. The dog's firmware is untouched (design:
`orchestrator/docs/design/VOICE_RELAY_BRIEF.md` and
`NAVIGATION_MAPPING_BRIEF.md` §Vision satellite).

| Stream | Transport | Consumer |
|---|---|---|
| PDM microphone, 16 kHz mono int16 | UDP to the adapter host, port 5005, 20 ms packets with a 4-byte sequence prefix | `dog/app/ears.py` → whisper → `voice.phrase` events |
| OV2640 camera, QVGA JPEG | HTTP on the XIAO, port 80: `/stream` (MJPEG), `/snap` (one frame), `/` (status JSON) | host-side YOLO (next session) |

## Build and flash

```
cp xiao_sense/secrets.h.example xiao_sense/secrets.h   # fill in SSID, password, adapter host
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --board-options "PSRAM=opi,PartitionScheme=default_8MB" satellite/xiao_sense
arduino-cli upload  --fqbn esp32:esp32:XIAO_ESP32S3 --port COMx satellite/xiao_sense
```

`PSRAM=opi` is required: the camera frame buffers live in PSRAM. The
arduino-cli bundled with Arduino IDE 2 works (see
`orchestrator/docs/reports/AUDIT_2026-09-02.md` §10 for its path). Serial is
the USB-CDC port at 115200; the sketch prints WiFi address, mic and camera
state at boot and a packet counter every 10 s.

## Bench validation (before it goes on the dog)

1. Power from the PC's USB-C. Watch the serial log: `WiFi: <ip>`, `Mic: PDM @16 kHz`,
   `Camera: OV2640 ready`.
2. `GET http://<xiao-ip>/` → status JSON with `"mic":true,"camera":true`.
3. `GET http://localhost:15001/api/robots/bittle-1/ears` on the adapter →
   `"streaming": true` and `packets` climbing, `dropped` near zero.
4. Say "Hey Laika, sit down" near the board → `ears/transcripts` shows the
   line with `wake: true, intent: sit`; the dog (or Mocha) runs `idle_sit`.
5. Open `http://<xiao-ip>/stream` in a browser for the picture.

Tuning knobs at the top of the sketch: `MIC_GAIN_SHIFT` (raise if `ears`
never sees speech, lower if it clips), `FRAME_SIZE`, `JPEG_QUALITY`.
On the adapter: `EARS_ENERGY_FLOOR` (speech gate), `WHISPER_MODEL`
(`base` default; `small` is more accurate and ~3× slower on CPU).

## Power on the dog

Two jumpers from a spare Grove socket's VCC/GND to the XIAO's 5V/GND pins.
Meter the socket first and stream for several minutes while watching the
dog's WebSocket stay up and the battery reading in the Power panel
(WiFi bursts peak ~340 mA). A LiPo on the XIAO's battery pads is the
fallback if the rail sags.
