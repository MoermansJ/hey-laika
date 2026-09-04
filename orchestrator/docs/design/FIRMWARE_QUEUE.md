# Firmware queue — changes waiting for the next flash

**Why this file exists:** flashing the BiBoard is a hands-on ritual (hold
BOOT, tap Reset, then esptool with no reset, see `../robot/HARDWARE.md`
"Firmware flash"), and 2026-09-04 showed it can take many tries. Firmware
changes are therefore pooled here and flashed together, at a calm moment,
with the dog on the floor and the greeting disabled. The satellite has its
own, easier ritual (USB-C, no buttons, esptool `--no-stub`) but needs
unwiring from the dog, so it gets a queue too.

Rule: every entry says what is built, what is verified without the dog,
and what the bench check after flashing is. The flashed state is recorded
in `../robot/HARDWARE.md` (firmware row) and the audit reports.

## BiBoard (hey-laika fork, `opencat-esp32/`)

Flashed now: fork commit `6b57e93` (speaker) **plus the scratch diagnostic
hook** built 2026-09-04 (prints `WIFI-DIAG` lines). Everything below is
committed in the fork but not on the dog.

| # | Change | Commit | Built? | Bench check after flashing |
|---|---|---|---|---|
| 1 | Drop a command whose String allocation failed instead of `strcpy(NULL+1)` panicking; log WiFi SSID tried and disconnect reasons at the default level | `a51fd08` | yes (`scratchpad/fw/fix`, rebuild from the fork) | `POST /mouth/play` with `CHUNK_BYTES` temporarily 1800 must answer "command dropped, out of memory" on serial, not reboot |
| 2 | `XW1%SSID%pass` writes the esp-wifi primary slot; `XW1` shows it (the stock `w%` command is intercepted by the loop's BOOT check on this board) | `2c1b3c4` | yes, 89 % flash (`scratchpad/fw/fix` holds both 1 and 2) | `XW1%<router>%<pass>` over serial, reboot: joins the router first, no 25 s hotspot detour; `XW2` can then go back to the iPhone |

Wanted next (not started):

- The loop's BOOT check (reaction.h ~line 219) fires on the PC's DTR line
  and clears the WiFi primary after 2 s. Debounce it to a real button press
  (e.g. require 300 ms low before acting) so opening a serial port cannot
  reboot the dog.
- Push the IMU pitch/roll and the exception direction/force angle to the
  host (SENSOR_DATA.md "left on the table").

## Satellite (`satellite/xiao_sense`)

Flashed now: the 2026-09-04 build (P9813 LED, `/led`, ESP-IDF I2S mic).

| # | Change | Built? | Bench check |
|---|---|---|---|
| 1 | Native `rainbow` LED effect (smooth hue sweep in `pumpLed`), replacing the host-stepped cycle in `mood.py` | not started; host version shipped instead | `/led?effect=rainbow&periodMs=4000` sweeps smoothly |
| 2 | Lower WiFi TX power (`WiFi.setTxPower`) and re-enable modem sleep between audio packets: the head-mounted radio only has to reach the router | not started | ears `dropped` stays ~0 for 5 min; XIAO `rssi` at the router unchanged |

## How to flash the queue

1. Dog on the floor, `POST /api/robots/bittle-1/greeting/disable`.
2. Build from the fork per `../robot/HARDWARE.md` and the memory recipe;
   flash with the owner at the buttons; read the banner with DTR/RTS
   released.
3. Run every bench check in the table, then move the rows into the
   "flashed now" line and date the HARDWARE.md firmware row.
