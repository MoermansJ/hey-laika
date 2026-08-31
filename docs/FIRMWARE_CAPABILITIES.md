# BiBoard Firmware Capability Catalog — Beyond What We Use

**Date:** 2026-08-31
**Source:** full mine of `F:\projects\robot\opencat-esp32` (snapshot `B10_260820`, a modified Petoi fork). Our robot runs `B10_251121` — items marked ⚠ are newer-tree features that must be verified live before relying on them.
**Already in use elsewhere:** serial + WiFi WS transports, `k` skills, `I/i` joint moves, `j` readback, `b` tones, `P` voltage, `?` banner, `w%` WiFi provisioning, `gp/gP` IMU stream, closed-loop turns, IMU exception lines, voice-module passthrough (see `SPATIAL_MVP_REVIEW.md`).

Build flags on this board: `BITTLE` + `BiBoard_V1_0`, NVS persistence (no I2C EEPROM), `BT_BLE` + `BT_SSP` + `BT_CLIENT` + `WEB_SERVER` + gyro all on. **No IR pin, no NeoPixel pin** on this board revision.

## A. Motion / joint control (stock hardware)

| Capability | Token | Notes |
|---|---|---|
| Sequential joint moves | `m idx ang …` (ASCII) / `M` (binary) | Pairs applied one at a time, 10 ms apart |
| Full 16-joint frame | `L` + 16 int8 | Single-shot posture transform |
| Sinusoidal signal generator | `o res speed [joint mid amp freq phase]…` | Up to 12 joints, procedural motion sweep |
| CPG gait oscillator | `r …` / `Q` + 12 int8 | Continuous parametric gait; `rg` runs an 8-gait demo; disables gyro balancing |
| Tilt setpoint | `t axis angle` | Shifts the balance target (lean on command) |
| Balance slope tuning | `l roll pitch` (-2..2) | How strongly the IMU corrects posture |
| Servo stiffness | `;` soft / `:` hard | Undocumented; writes P-gain to all servos |
| Gait speed | `.` faster / `,` slower | Adjusts runDelay 0..20 |
| Shut one servo | `d <idx>` (`d` alone = rest all) | |
| Pause/resume | `p` | Echoes `P` paused / `p` resumed |
| **On-board task queue** | `q<tok><cmd>:<ms>><tok><cmd>:<ms>>` | Multi-step scripts sequenced by the firmware itself — e.g. `qk sit:1000>m 8 0 8 -30:500>` |
| Random-behavior mode | `z` (echo `Z`/`z`) | Built-in idle "life": weighted random skills, auto-rest after 60 s idle. Expect unsolicited motion + echoes |

## B. Servo feedback / kinesthetic teaching (stock board; needs feedback-capable servos)

| Capability | Token | Notes |
|---|---|---|
| Read TRUE servo angles | `fp` (once) / `fP` (stream) / `f<idx>` | From servo potentiometers — unlike `j`, detects stalls/obstructions. Non-feedback servos are auto-skipped |
| Puppet mode | `F` on / `f` off | Move one leg by hand, others mirror it |
| **Learn-by-drag recording** | `fl` | Pose the robot by hand; firmware records ≤125 frames × 11 joints and prints an optimized skill array |
| Replay learned motion | `fr` | |
| Auto-calibrate via feedback | `c 16` | Blocking |

## C. Calibration / config / persistence (stock)

| Capability | Token | Notes |
|---|---|---|
| Joint calibration | `c idx off …`; `c idx ±1001..±1009` for ±1..9° nudges | `s` saves, `a` aborts |
| IMU calibration | `gc` (5 s countdown) / `gci` (now) | **Blocks ~15 s** — host must not send during it |
| Gyro controls | `gU/gu` task on/off, `gB/gb` balance, `gF/gf` sample rate, `g?` state | |
| Rename robot | `n<Name>` (≤16 chars) / `n` reads | Sets BLE/BT names (`<ID>_BLE`, `<ID>_SSP`) next boot — the dog could literally be "Laika" |
| Buzzer volume/mute | `b<0..10>` / `b` toggles mute+boot melody | Persisted |
| Meow | `u` | Random-parameter meow; distinct fall-over chirp exists |
| Melody player | `b n1 d1 n2 d2 …` / binary `B` | Up to ~1250 notes |
| Factory reset | `!` | Next boot runs the QA flow (prompts `Y/n` on serial!) |
| **Raw GPIO** | `Ra/Rd <pin>` read, `Wa/Wd <pin> <val>` write (binary) | Host-driven IO on free pins — e.g. PWM_LED_PIN 27, ANALOG1 34 |

## D. Skills / behavior data (stock)

| Capability | Interface | Notes |
|---|---|---|
| **Upload skill at runtime** | `K` + binary array (≤2507 B) | 125-frame behavior / 312-frame gait; stored to NVS `tmp`, runs immediately. Pairs with `fl` output |
| Re-run uploaded skill | `T` | |
| Random built-in skill | `kx` | Excludes risky ones (flips, jumps…) |
| Full skill table | 92 named skills | Incl. unused-by-us: `pee, lucky, showOff, hsk` (handshake), `fiv` (high five), `clap, hunt, snf` (sniff), `wh, chr, dg, kc, hg` (hug), `pu/pu1` (pushups), `mw, tbl, flip…` |
| Joystick protocol | `J` binary (x,y or button payload) | Emulates the mobile app's control pad |

## E. Transports beyond USB + WS

| Transport | Interface | Notes |
|---|---|---|
| **BLE UART** | Nordic UART Service, name `<ID>_BLE` | Full token protocol; TX chunked at 10 B — reassemble lines. Bare `g` is rewritten `gf/gF` |
| **Classic Bluetooth SPP** | `<ID>_SSP`, auto-pairs | Read at HIGHER priority than USB serial |
| BLE client mode | Boot-time 3 s scan for a `BBC` (micro:bit) peripheral | ⚠ If found, the BLE server never starts; server also absent for first ~3.5 s of boot |
| **Grove UART (Serial2)** | 115200 on pins RX 9 / TX 10, module `XS` (default ON) | A 4th command port — a Pi/MCU riding the dog could drive it without USB |
| WS extras | `results[i]` = captured output of command i; one task group at a time (second concurrent → error); `b64:` for all binary tokens | Already partially used |
| WS push events | `event_cam` (x,y,w,h), `event_us` (distance) | Needs camera / ultrasonic module |
| Boot button GPIO0 | press = reboot to WiFi-manager; 10-count hold = clear WiFi creds | |

## F. Modules (`X` token) — mostly extra hardware

- `X?` lists module codes + activation flags; `X<upper>` enable / `X<lower>` disable, persisted (`moduleState`).
- **Stock, no hardware:** `XS` Grove serial (default on), `XQ` touch demo on pin 34.
- **Add-ons:** `XA…` voice (language switch, reaction toggle, 10 learnable custom phrases), `XU` RGB ultrasonic (+ `C r g b idx effect` eye colors), `XG` gesture, `XC` camera (Mu3 / Sentry / Grove Vision AI V2 — ⚠ enabling camera turns the IMU off), `XI` PIR, `XT` touch, `XL` light, `XD` IR distance, `XB` 4-zone back-touch pad (enabled by default if installed — free async petting events!).
- **Unavailable on this board:** IR remote, NeoPixel, MP3, OLED (no pins / not compiled). Pin-27 LED can still be driven manually via `W`.

## G. Unsolicited lines a host must tolerate

- Boot banner sequence ends in `Ready!`; after `!` reset the firmware **prompts** `Run factory quality assurance program? (Y/n)` and waits.
- `Low power: <V>V…` + melody every 10 s, forces rest; `Got <V> V power` on recovery.
- IMU exceptions: fall over, knocked, `Pushed` (+ direction + `ForceAngle:`), free fall (plays `lnd`), lifted/dropped, off-direction auto-correct, `endTurn`.
- `G`/`g` emitted on any implicit gyro-balance change; `gP` streams full 6-axis (accel + ypr), prefixed `ICM`/`MCU`.
- Firmware config auto-wipes when flashed firmware is newer than the stored stamp (calibration/name/modules reset after upgrades).

## H. Defined but dead

`x` (T_LEARN) has no handler (`fl`/`fr` is the real learn path); `w` servo-microsecond and `o` melody variants are compiled out.
