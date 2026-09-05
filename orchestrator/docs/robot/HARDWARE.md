# Bittle X Hardware Reference

**Updated:** 2026-09-03 (sensor suite installed: ranger, satellite, mood light, speaker) · Facts validated live unless noted.

## The robot

| | |
|---|---|
| Model | Petoi **Bittle X V2** (voice edition) |
| Controller | **BiBoard V1.0** — ESP32 (WiFi + BLE + classic BT), IMU ICM42670 at I2C 0x69 |
| Firmware | **hey-laika fork** of OpenCat ESP32 (source `F:\projects\robot\opencat-esp32`, B10_260820 snapshot over upstream `9ebb48a`): firmware-reset Phase A cuts 1, 3, 4 done, cuts 2 and 6 partial, cuts 5, 7–10 not started, plus leash/nav additions (`XW` tools, 1 Hz `event_rssi`, second SSID slot, dead-man). Base version **B10_251121** with the date pinned, so the robot still reports `B10_251121` over the wire. **Flashed 2026-09-04 18:00: fork `fce29da`** (Grove serial off, LEDC PWM speaker with 4 KB prebuffer and `XWf`, IRAM-safe ISR, OOM guard, `XW1`); the flash ritual and batch folders are in `../design/FIRMWARE_QUEUE.md`. Detail: `../design/FIRMWARE_RESET.md` status line, `../reports/AUDIT_2026-09-02.md` §4 |
| Battery | 2S LiPo 7.4 V nominal, 1000 mAh (JST-XH). Full ≈ 8.35 V, firmware low-power floor ≈ 6.8 V, cutoff behavior: rest + melody every 10 s. Long-press the battery's own button to power servos |
| USB | CH343 USB-UART, enumerates as **COM3** on the dev machine, 115200 8N1. **DTR drives the BOOT pin, RTS is not wired to EN**: open the port with DTR and RTS released (pyserial: set `dtr=False, rts=False` before `open()`), or the firmware sees BOOT pressed, prints "reboot and use Wifi manager", and restarts (held >2 s it also clears the primary WiFi slot). No PC-side sequence enters download mode; see the flashing note in `../design/ARRIVAL_DAY_RUNBOOK.md` §4c |
| Firmware flash | Hardware reset with BOOT low: hold BOOT, tap Reset, release, then `esptool --chip esp32 --port COM3 --before no_reset write_flash …` (binaries from `arduino-cli compile --output-dir`). Fallback: battery off, USB unplugged, hold BOOT, plug USB in. A software restart keeps the last latched strapping value, so BOOT-then-`ESP.restart()` does not work |
| WiFi slots | esp-wifi primary (stock `w%` path, currently empty after the 2026-09-04 clears) and the fork's secondary in Preferences (`XW2%SSID%pass`, currently the home router). Boot tries primary then secondary |
| Voice module | Onboard (Bittle X): mic + "Hey Bittle"-style hotword on a separate MCU wired to Serial1; emits unsolicited `X…` lines |
| Speaker | Onboard buzzer (melody/tone). Plus, since 2026-09-03, a **Grove Speaker Plus** (2 W amp + speaker, volume pot) on **GPIO 10**: the speaker cable's **yellow** (its SIG, Grove pin 1) joins the **white lead** (pin 2, GPIO 10) of the Grove-to-jumper cable in the **UART socket, the one whose yellow lead carries the ranger**; the speaker's own white is unused; its red and black come from another socket's red and black (power only, any socket). Firmware playback is 8-bit LEDC PWM at 62.5 kHz (`XWp/XWa/XWf/XWq`, 4 KB prebuffer), fed 8 kHz unsigned PCM in 1 KB frames (larger frames stall the WebSocket layer), walkie-talkie quality. `SPEAKER_PIN=10`. Since fork `807e7a5` the Grove serial module is off, so nothing else drives GPIO 10. Lesson of 2026-09-04: the speaker's yellow had been on the XIAO's D2 (the LED clock line) and later on the wrong socket; "loud ticks", "crackle" and "silence" were all wiring, and the firmware's speaker path had never been heard until 17:40. The Speaker Plus **volume pot** is the last variable: at its evening setting playback was buzz and distortion, and one adjustment of the pot made barks and speech clean (18:15). Check the pot before suspecting anything else |
| Sensor suite | Ultrasonic ranger, satellite camera + microphone + mood light, IMU, battery, WiFi RSSI and fingerprints, pose. What each yields: `SENSOR_DATA.md` |
| Not present on this board | IR receiver, NeoPixel, OLED, MP3 module |

## Servo map

16 firmware joint indices; **9 physical servos** on Bittle X — indices 1–7 are
placeholders that report 0 and ignore writes. Angle limits are the adapter's
safety clamps (`dog/app/robot_schema.py`), not firmware limits.

| Index | Joint | Range |
|---|---|---|
| 0 | Head pan (neck yaw — the only head axis; no tilt servo) | -90..90° |
| 8 / 9 | Front left / right hip | -60..60° |
| 10 / 11 | Back right / left hip | -60..60° |
| 12 / 13 | Front left / right knee | -90..30° |
| 14 / 15 | Back right / left knee | -90..30° |

Servos have no position feedback in `j` readback (commanded angles only);
firmware `fp` can read true angles **if** feedback-capable servos are
installed (unverified on this unit). Firmware interpolates moves at
~4 ms/degree and echoes on completion.

## Network

| | |
|---|---|
| WiFi | Provisioned 2026-08-31 (`w%SSID%password` over USB, credentials persist in ESP32 NVS, auto-reconnects each boot) |
| IP | **192.168.0.246** (DHCP — keep a router reservation) |
| Command endpoint | WebSocket `ws://192.168.0.246:81` (see `NETWORK_API.md`) |
| Other transports | USB serial, BLE UART (`<ID>_BLE`), classic BT SPP (`<ID>_SSP`), Grove UART on pins 9/10 |
| Ultrasonic ranger | Grove one-pin ranger, SIG on **GPIO 9**: the ranger's **yellow** on the **yellow lead** of the UART socket cable (the same cable whose white lead is the speaker), red and black from that cable too. Proof the cable is in the UART socket: `GET /senses/range` with a hand in front returns a distance (19 cm on 2026-09-04); on any other socket it returns null. Validated 2026-09-03: one-shot `XU` reads, 0 misses in 120 reads on a stationary target, ~2 m window, `-1` = no echo. `ULTRASONIC_PIN=9` |
| Satellite | XIAO ESP32S3 Sense on the head, own WiFi at **192.168.0.189** (flashed 2026-09-03, MAC 68:ee:8f:50:ec:5c; `SATELLITE_HOST`, reserve its DHCP address), powered from analog socket A. OV2640 camera (QVGA JPEG, `/snap` + `/stream` on port 80), PDM mic (PCM over UDP to the adapter), Grove Chainable RGB LED (P9813), cable in the LED's **IN** port (in OUT it never responds, at any voltage), **yellow on D2 (clock), white on D3 (data), red on the XIAO's 3V3 pin, black on any BiBoard socket ground** (the grounds are common through the XIAO's feed), **never the 5 V socket** (P9813 input threshold is 0.7 × VDD: at 5 V the XIAO's 3.3 V never registers, the driver stays in its power-on state and the LED is stuck pure white; found 2026-09-04), driven through `/led`. Sketch: `satellite/xiao_sense` |
| Reset WiFi | Hold the boot button (GPIO0) through its 10-count at startup |

## Cabling plan (agreed 2026-09-05, before the tidy-up)

Sockets before: UART (ranger SIG on 9, speaker SIG on 10, ranger power),
analog A (XIAO power only), a third socket (speaker power only), a socket
ground for the LED. One socket of four carries a signal.

| Step | Change | Why |
|---|---|---|
| 1 | LED black moves from a BiBoard socket ground to the XIAO's single GND pin (shared with the BiBoard ground wire, two wires on one pin) or spliced into the XIAO's black lead | The LED becomes a self-contained head unit on the XIAO; frees a socket |
| 2 | Speaker red/black move onto analog A next to the XIAO's power, through a Grove Branch Cable (one plug to two) or a splice | All sockets share the one 5 V regulator, so only the connector changes; frees a socket |
| 3 | UART cable untouched: yellow = ranger on GPIO 9, white = speaker on GPIO 10 | Those GPIOs exist only on that socket; moving a signal changes `ULTRASONIC_PIN` / `SPEAKER_PIN` and the firmware |

After: UART and analog A in use; I2C (GPIO 21/22, the VL53L ToF mount in
`noncodefiles/stl`) and analog B (GPIO 36/39) free.

Rules for the pass:

- **Label both signal leads of the UART cable at both ends** (yellow =
  ranger, white = speaker). The 2026-09-04 speaker hunt was this cable.
- **Service loop at the neck** for every head cable (XIAO power, LED, and
  the speaker if on the head): the head pan servo sweeps 180°; test the
  full sweep by hand after tying down.
- **Antenna** lead away from the servo and the BiBoard, antenna clear of
  metal; the satellite read -84 to -90 dBm against the BiBoard's -61 dBm
  from the same router on 2026-09-05. Retest `/satellite` → `rssi`.
- **Air around the XIAO**: no foam or tape over it, no contact with a
  servo housing, camera ribbon not folded tightly. It has no thermal
  protection of its own (see `SENSOR_DATA.md`).
- **Speaker goes on the head** (top, or forward out of the mouth). It sits
  centimetres from the mic on the XIAO, so the ears must be muted during
  playback; that guard is still to be written.
- **Volume pot facing outward.**
- **Camera** aimed forward, not at the desk (2026-09-05 frames were black
  for that reason).

## Care and feeding

- The firmware **silently drops** commands received while busy — every host
  exchange must await the completion echo (serial) or `completed` task frame (WS).
- IMU calibration (`gc`) blocks the firmware ~15 s; never send during it.
- After a `!` factory reset the firmware prompts `Run factory quality
  assurance program? (Y/n)` on serial and waits.
- See `FIRMWARE_CAPABILITIES.md` for the full command/feature catalog and
  `VALIDATION_RESULTS.md` for the raw live protocol captures.
