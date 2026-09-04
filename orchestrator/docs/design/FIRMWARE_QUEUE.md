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

Flashed now: fork commit `fce29da` (rows 1-6, batch 3, flashed 2026-09-04
18:00; `fce29da` also puts the ring accessors the ISR calls in IRAM). Bench
result the same evening: speech, barks and test tones play continuously
through the Speaker Plus, walkie-talkie quality, once the wiring matched
`../robot/HARDWARE.md`. Rows 1-6 stay listed until their individual bench
checks are ticked; the OOM guard (1), XW1 (2) and the crash path (4) are
still unchecked. Rows are moved out of the table once their bench check
has passed, not when flashed.

| # | Change | Commit | Built? | Bench check after flashing |
|---|---|---|---|---|
| 1 | Drop a command whose String allocation failed instead of `strcpy(NULL+1)` panicking; log WiFi SSID tried and disconnect reasons at the default level | `a51fd08` | yes (`scratchpad/fw/fix`, rebuild from the fork) | `POST /mouth/play` with `CHUNK_BYTES` temporarily 1800 must answer "command dropped, out of memory" on serial, not reboot |
| 2 | `XW1%SSID%pass` writes the esp-wifi primary slot; `XW1` shows it (the stock `w%` command is intercepted by the loop's BOOT check on this board) | `2c1b3c4` | yes | `XW1%<router>%<pass>` over serial, reboot: joins the router first, no 25 s hotspot detour; `XW2` can then go back to the iPhone |
| 3 | Grove serial module off in the BiBoard V1.0 default table, and `XWp` ends `Serial2` and clears the module flag. GPIO 10 is TX2: with the module on, every `printToAllPorts` line went into the Speaker Plus as a loud tick (the 2026-09-04 "bark" was six ticks, one per acknowledged frame), and the ranger's echoes on GPIO 9 (RX2) were read as commands that abort gaits | `807e7a5` | yes, 89 % flash, all four rows in one image: `noncodefiles/fw-build/2026-09-04-batch/` (`flash.cmd` has the esptool line) | Banner shows `Grove_Serial` 0 in the module list; `?` over the Control tab produces no tick from the speaker; `POST /mouth/play {"sound":"positive_bark"}` is a bark |
| 4 | Speaker ISR writes `GPIO_SIGMADELTA0_REG` directly instead of the flash-resident `sigmaDeltaWrite`, and the `spkPin` NVS write moves ahead of `timerAlarmEnable`: an IRAM timer ISR that runs during an NVS write (cache disabled) crashes the board | `807e7a5` | yes (same image) | With the speaker attached, `XW2%ssid%pass` (an NVS write) over serial must not reboot the dog; play a clip straight after |
| 5 | Speaker output is 8-bit LEDC PWM at 62.5 kHz on channel 7 (high-speed timer 3, which the 12 servos leave free) instead of the sigma-delta modulator. With rows 3-4 flashed, a 2 s 440 Hz tone (`batch2/tone_440hz_2s.wav` through `POST /mouth/wav`) came out as crackle with no note: the amplifier never averaged the 12 ns sigma-delta edges. The Speaker Plus is specified for PWM input | `6c013ca` | yes, 89 % flash, rows 1-5 in one image: `noncodefiles/fw-build/2026-09-04-batch2/` (`flash.cmd` now ends with `--after no_reset`: tap Reset yourself) | The 440 Hz tone is a clear note; `positive_bark` is a bark; mood-light changes while the speaker is idle do not crackle (if they still do, the amplifier's supply shares the satellite's rail and the fix is the speaker's red wire, not firmware) |
| 6 | Prebuffer: the ISR outputs silence until 4 KB (0.5 s) are queued or the host sends `XWf` after the last frame; a dry ring re-arms it. With rows 1-5 flashed and the wiring finally right (speaker yellow on the UART socket's white lead, GPIO 10), a 440 Hz tone, a 100 Hz square and a step pattern all came through and boosted speech was voice-like but cut out: 1 KB frames per ~100 ms round trip barely outpace the 8 kHz drain, so the ring ran dry on every WiFi hiccup. 1536-byte frames are not an option: they stall the firmware's WebSocket layer with no reply until a reboot (17:46) | `91cfbdc` | yes, 89 % flash, rows 1-6 in one image | `hey_laika_sit.wav` through `POST /mouth/wav` is continuous speech; `positive_bark` is a bark; a clip shorter than 0.5 s still plays (XWf) |

Wanted next (not started):

- The senses layer's automatic WiFi sniff (`XWs`, once a minute when the dog
  is quiet) blocks the loop ~2 s and drops the WebSocket every time (adapter
  log: "link lost during 'XWs'", all afternoon 2026-09-04). Either scan
  asynchronously in the firmware or stop auto-sniffing unless navigation
  is actually in use.

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

Not firmware, but found the same night and fixed by wiring: the P9813 mood
light never accepted a frame. Its input threshold is 0.7 × VDD (3.5 V on
the 5 V socket) and the XIAO drives 3.3 V, so the driver stayed in its
power-on state, all three sinks on, pure white. Power the LED from the
XIAO's 3V3 pin instead (threshold 2.3 V, VDD minimum 3.0 V); see
`../robot/HARDWARE.md` satellite row and `../../satellite/README.md`.

## How to flash the queue

1. Dog on the floor, `POST /api/robots/bittle-1/greeting/disable`.
2. Build from the fork per `../robot/HARDWARE.md` and the memory recipe;
   flash with the owner at the buttons; read the banner with DTR/RTS
   released.
3. Run every bench check in the table, then move the rows into the
   "flashed now" line and date the HARDWARE.md firmware row.
