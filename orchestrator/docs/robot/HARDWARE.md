# Bittle X Hardware Reference

**Updated:** 2026-08-31 · Facts validated live unless noted.

## The robot

| | |
|---|---|
| Model | Petoi **Bittle X V2** (voice edition) |
| Controller | **BiBoard V1.0** — ESP32 (WiFi + BLE + classic BT), IMU ICM42670 at I2C 0x69 |
| Firmware | **B10_251121** (stock OpenCat ESP32 build; reference clone at `F:\projects\robot\opencat-esp32` is snapshot B10_260820) |
| Battery | 2S LiPo 7.4 V nominal, 1000 mAh (JST-XH). Full ≈ 8.35 V, firmware low-power floor ≈ 6.8 V, cutoff behavior: rest + melody every 10 s. Long-press the battery's own button to power servos |
| USB | CH343 USB-UART, enumerates as **COM3** on the dev machine, 115200 8N1. Opening the port does **not** reboot the board |
| Voice module | Onboard (Bittle X): mic + "Hey Bittle"-style hotword on a separate MCU wired to Serial1; emits unsolicited `X…` lines |
| Speaker | Buzzer only (melody/tone capable). No MP3/DAC hardware |
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
| Reset WiFi | Hold the boot button (GPIO0) through its 10-count at startup |

## Care and feeding

- The firmware **silently drops** commands received while busy — every host
  exchange must await the completion echo (serial) or `completed` task frame (WS).
- IMU calibration (`gc`) blocks the firmware ~15 s; never send during it.
- After a `!` factory reset the firmware prompts `Run factory quality
  assurance program? (Y/n)` on serial and waits.
- See `FIRMWARE_CAPABILITIES.md` for the full command/feature catalog and
  `VALIDATION_RESULTS.md` for the raw live protocol captures.
