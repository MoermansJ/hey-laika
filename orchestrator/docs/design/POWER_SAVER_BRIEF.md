# Battery saver — tiers that trade liveliness for runtime

**Status:** built 2026-09-05 (`dog/app/power_saver.py`, card on the Activity
tab). Not yet measured on the dog: the drain per tier and whether the servos
re-engage cleanly after `d`.

## Why

Before this, saving battery meant the idle ladder (sit after a quiet minute,
lie down after two) and a rest at 5 %. Everything else ran flat out all day:
the camera polled at 4 fps, the LED sat at full brightness, the WiFi sniffer
scanned every quiet minute, and the servos held whatever pose she was in. On a
1000 mAh 2S pack the measured drain was 13 to 26 % per hour.

Where the power goes, from the parts list: servos holding a pose are the
largest draw and fall to zero once switched off (`d`); the satellite's camera
and WiFi bursts peak around 340 mA and scale with frames sent; the LED is up
to 60 mA at full white; the BiBoard itself and the microphone stream are the
floor that stays.

## The tiers

| Tier | Enters when | Camera | LED | Sniffer | Posture | Voice |
|---|---|---|---|---|---|---|
| active | default | 4 fps | full | on | as commanded | everything |
| eco | battery ≤ 30 % or quiet 5 min | 1 fps | 40 % | off | unchanged | everything |
| doze | battery ≤ 15 % or quiet 15 min | paused | 10 % | off | `power_nap`: lie down, then `d` (servos off) | everything |
| critical | battery ≤ 8 % | paused | 10 % | off | `power_nap` at safety priority | questions answered; motion tools refused with "My battery is too low to move. Please charge me first." Says "My battery is low. Please charge me." once |

The microphone stays on in every tier, so "Hey Laika" always works.

### The sensor gate

Independent of the tiers: the camera, the ranger and the WiFi sniffer run
only while she is moving, meaning a motion command in the last
`stationaryAfterS` seconds (20 by default, from the controller's motion
clock). Once she has been still that long they pause, and only the ears and
the speaker stay live. The next motion command brings them back at the tier's
rate. `sensorsWhenStationary` turns the gate off. The Vision tab's chips say
"paused (battery saver or manual)" and "paused while stationary"; the ranger
route answers from its last reading with `gated: true` instead of asking the
firmware.

A consequence worth knowing: while she is still, a person walking up is not
seen, only heard. "Hey Laika" is the way to get her attention.

Quiet time is the shorter of the idle ladder's motion clock and the time since
the last activity the saver saw. Activity is anything that shows someone is
there: `voice.wake`, `voice.phrase`, `voice.intent`, `conversation.listen`,
`vision.person`, every `leash.*` event, `exception.report` (lifted, knocked),
and any command sent through the adapter's command route. Activity lifts a
quiet-time tier back to active at once and restores the camera rate, the LED
and the sniffer.

A battery-forced tier does not lift on activity. It lifts when the level
climbs back above its threshold plus a hysteresis band (5 %), which is what
charging looks like, or on a manual override from the console.

## How it is wired

- `PowerSaver` evaluates every 5 s. It reads the battery from the telemetry
  cache and the quiet time from the event binder's idle clock, and listens to
  every framework event as a binder listener.
- The posture changes go through the framework like everything else: the
  `power.doze` and `power.critical` events are bound to the seeded
  `power_nap` behavior (`krest`, then `d`). Lifecycle priority for doze,
  safety priority for critical. Changing what dozing looks like is a binding
  edit.
- The camera rate and pause use `EyesService.set_fps` / `set_enabled`; the LED
  uses `MoodService.set_dim`, a scale applied to every brightness the moods
  send, so the moods themselves are untouched; the sniffer is its `enabled`
  flag.
- The conversation asks the saver before running a behavior tool
  (`motion_allowed`), and speaks the refusal instead in critical.
- Thresholds, quiet times, the eco frame rate and the two dim levels live in
  the settings table (`power.saver`) and are edited on the card.
- `POWER_SAVER_ENABLED=False` turns the loop off; the status route still
  answers.

## Console

Activity tab, "Battery saver" card: the tier as a badge coloured like the
matching LED mood, how long and why, battery and quiet time, the four tiers
as cells with the active one lit, buttons Auto / Wake / Eco / Doze (Wake,
Eco and Doze hold the tier until Auto), and the thresholds behind a
disclosure.

## To verify on the dog

1. After `d`, does the next skill command re-engage the servos, or does the
   arbiter need an explicit `kbalance` first? If the latter, `power_nap`'s
   inverse belongs at the front of the wake path.
2. Drain per tier over an hour each, from the power sessions, to replace the
   parts-list estimates with numbers.
3. Whether 10 % LED is visible enough in a lit room to still read the
   listening pulse. If not, raise `dozeLedDim` on the card.

## Left on the table

- The satellite cannot be powered down from the BiBoard, and the sketch has
  no camera-sleep endpoint. Putting the OV2640 into standby in doze would save
  the most on the satellite side; it needs a `/camera?on=0` handler in the
  sketch and a flash.
- The microphone stream is the floor. An on-device energy gate on the XIAO
  (send packets only above a threshold) would cut WiFi transmit time in a
  quiet room by most of it, at the cost of losing the level meter's idle
  readings.
- Drain-aware predictions: the power tracker's "minutes left" is a single
  average; per-tier rates would make it honest.
