# Planning Brief — Proximity Leash (phone-tethered Laika)

**Date:** 2026-09-01 (rev 2) · **Status:** planning input
**Goal:** the dog stays connected to WiFi (orchestrator keeps full control over the
existing WS channel) while being *virtually leashed* to the owner's smartphone:
it knows roughly how far the phone is and reacts through the behavior framework —
warn, stop, and finally rest — when the leash is stretched or lost.

**Owner's phone:** iPhone 15 Pro (matters twice: iOS backgrounding rules for the
optional BLE path, and its U2 chip for the UWB upgrade path).
**Standing assumption (from the owner):** dog and phone are always on the same
WiFi — the home network at home, the iPhone's personal hotspot when out.

---

## 1. Candidate distance signals

| Signal | dog↔phone? | Phone software? | Verdict |
|---|---|---|---|
| **Dog-side WiFi RSSI of the AP, when the AP *is* the phone's hotspot** | ✅ direct | **None** | ✅ **Primary (away mode).** `WiFi.RSSI()` is one call in firmware we own; the phone is the anchor by definition. |
| **BLE: iOS app connects to `<ID>_BLE`, `readRSSI()` ~1 Hz** | ✅ direct | Small iOS app | ✅ Optional refinement — works at home too; see §5. |
| **UWB: Nearby Interaction (U2) ↔ DW3000 module on the dog** | ✅ ±10–30 cm + bearing | iOS app | ✅ Upgrade path — see §6. |
| Dog-side WiFi RSSI of the *home* AP | ❌ measures dog↔router | None | ❌ At home the router is the anchor, not the phone. Two radii from the router don't give dog↔phone (opposite-sides problem). "Same WiFi" ≠ proximity unless the phone *is* the AP. |
| ESP32 promiscuous-mode sniffing of the phone's WiFi frames at home | ✅ in principle | None | ❌ Rejected: real but heavy — promiscuous callback + MAC filter under WiFi/WS/servo load, phone transmits sparsely when idle (needs induced traffic), iOS private-MAC bookkeeping. Not worth it given away-mode is the actual leash use case. |
| WiFi RTT (802.11mc FTM) | — | — | ❌ Classic ESP32 (BiBoard V1) has no FTM support, and iPhones don't speak 802.11mc anyway. |
| Dog scans for phone's BLE advertisement | — | — | ❌ Rejected in rev 1: firmware scan under coexistence pressure; iOS MAC rotation. |
| Find My / iCloud location | — | — | ❌ GPS-coarse, no sanctioned API. |

**Consequence:** the leash is **mode-based**, and the primary mode needs *nothing
running on the phone*:

- **Away mode (the real leash use case — out on a walk):** dog joins the iPhone's
  hotspot; the phone is physically the WiFi anchor. The dog measures its own
  signal to the phone and reports it up the existing WS. App-free.
- **Home mode:** there is no phone-anchored distance without extra software, and
  arguably no need for one — the dog is allowed to roam the house. App-free
  *presence* is still available (orchestrator pings/ARPs the phone's IP →
  "owner home" arming/geofence events). If a true at-home leash is ever wanted,
  the BLE path (§5) provides it.

---

## 2. Away-mode architecture (app-free)

```
iPhone hotspot (the AP — always on the owner)
   ▲ WiFi                         ▲ WiFi
   │                              │
  Dog (firmware: push {"type":"event_rssi","rssi":-52,"timestamp":…} ~1 Hz)
   │  ws://dog:81  (existing channel, no new surface)
   ▼
Adapter (on the laptop, joined to the same hotspot)
   ├─ LeashService: median-of-5 → EMA → zone machine w/ hysteresis + dwell
   │     near → warn → far → lost   (lost also on frame silence / WS drop)
   ├─ zone events → behavior bindings (arbiter):
   │     leash.warn → stop gait, sit, bark        [lifecycle prio]
   │     leash.far  → stop + periodic bark        [lifecycle prio]
   │     leash.lost → rest                        [safety prio]
   └─ → orchestrator STOMP /topic/robot/{id}/leash → GUI leash widget
```

- **LeashService lives in the adapter** (rev 2 change): the signal now arrives on
  the adapter's WS, the reactions execute in the adapter's arbiter, and away mode
  runs the whole stack on the laptop anyway. The orchestrator proxies settings
  and streams zone/RSSI to the GUI, per the usual pattern.
- Zones/bindings/calibration are identical regardless of signal source — BLE or
  UWB later just swap the input into the same state machine.

### The one hard safety nuance

When the leash breaks by *losing WiFi entirely* (dog walks out of hotspot range),
**the host cannot command the rest** — the WS is gone. Post-reset firmware is a
silent machine and will keep doing whatever was last commanded. Away mode
therefore needs a small **firmware dead-man**: no WS client (or no heartbeat) for
N seconds → self-`rest`. This is the single genuine firmware *behavior* addition,
and it is justified exactly the way the reset doctrine allows: it is a safety
floor, not personality. (At home the adapter's connection is effectively
permanent, so the dead-man should be armed only in leash/away mode — or use a
generous N like 15–20 s so it never fires spuriously at home.)

### Firmware additions (all small; we own the fork)

1. **`event_rssi` push frame** (~1 Hz while a WS client is connected), mirroring
   the existing `event_us` pattern — or a polled token if push is undesirable.
   (Verified: nothing in the current source reports `WiFi.RSSI()` today.)
2. **Multi-SSID credentials** — NVS currently stores one network
   (`w%SSID%password`); the dog needs home SSID + hotspot SSID with
   try-in-order, so leaving the house needs no re-provisioning.
3. **Dead-man rest** on WS-client silence (above), armed by a command/flag.
4. *(Optional, BLE path)* `esp_ble_tx_power_set()` exposure — see §4 knobs.

> Consolidated cross-brief firmware list (adds the WiFi scan token for
> fingerprinting): `docs/design/NAVIGATION_MAPPING_BRIEF.md` §6 — one fork, one
> flash session covers everything.

### Away-mode operational requirements

- **iPhone hotspot must have "Maximize Compatibility" ON** — the ESP32 is
  2.4 GHz-only and cannot see a 5/6 GHz-only hotspot.
- **The adapter must be on the hotspot too** (the dog doesn't dial out) — i.e.
  the laptop comes along, running adapter (+ orchestrator/GUI if wanted; the
  phone's browser can then open the GUI over the hotspot). A future
  "dog-dials-out" transport would remove the laptop; out of scope here.
- iOS personal hotspot idles down with zero clients; the laptop + dog being
  joined keeps it up. Expect a beat of reconnection churn when the phone sleeps.

---

## 3. Link budget & margins (what leash lengths are realistic)

Physics is the same for both radios — log-distance rolloff ≈ 6 dB per doubling
(open air), so **any threshold has a "half to double" worst-case band**; smoothed
noise is ±3–4 dB, but body occlusion (phone in pocket, dog behind you) adds slow
±5–15 dB shifts that averaging cannot remove. Design accordingly: zones, not
meters; ~6 dB hysteresis (≈1.5–2× in distance) between trip and recover.

**Away mode (dog reads the hotspot):** iPhone hotspot transmits ~+14–20 dBm; the
dog should see ≈ −35…−45 dBm at 1 m, rolling to the ESP32's usable floor around
−85…−90 dBm at roughly **40–60 m open air** — beyond which WiFi itself drops and
the dead-man is the leash. Usable zone boundaries: ~3 m up to ~25–30 m.

**BLE path (reference, from rev 1):** ESP32 advertises at default +3 dBm → iPhone
sees ≈ −60 dBm at 1 m, −80 at 10 m, "lost" ≈ 35–40 m open air / ~10 m + a wall
indoors. ~30 dB dynamic range ⇒ about five distinguishable 6-dB zones.

---

## 4. Calibration, not conversion

- **Walk-test capture mode** in the GUI: start capture, walk to the intended
  leash boundary, mark it; LeashService records the smoothed RSSI there.
  Thresholds come from marks, never from a path-loss formula.
- Hysteresis + dwell (2–3 s) on every transition; thresholds/dwell are
  per-robot, per-mode settings in the leash widget.
- **Knobs:** away-mode leash length is set purely by thresholds (hotspot power
  isn't ours to change). On the BLE path, `esp_ble_tx_power_set()` (−12…+9 dBm)
  coarse-scales the whole geometry: −12 dBm shrinks "lost" to ~8 m for a crisp
  short leash; +9 dBm roughly doubles distances vs default.

---

## 5. Optional BLE path (iOS-resolved, needs a phone app)

Only needed if a true *at-home* phone-anchored leash is wanted. iOS specifics
(rev 2, replacing rev 1's passive-scan choice which suited Android):

- Foreground scanning works (firmware advertises Nordic UART service UUID
  `6E400001-…`, which iOS background filtering requires), but backgrounded
  scanning is throttled/coalesced → sparse RSSI.
- **Robust iPhone pattern: connect to `<ID>_BLE` and call `readRSSI()` on a ~1 s
  timer** with the `bluetooth-central` background mode. Clean 1 Hz RSSI, and the
  disconnect event is an instant unambiguous `leash.lost`. Rev 1's "a connected
  client stops advertising" caveat is moot — the leash *is* the client. Firmware
  already budgets for a live BLE link (WS heartbeat +15 s while BLE active).
- App: SwiftUI + CoreBluetooth, POSTs `{rssi|null, ts}` at 1 Hz to the
  orchestrator leash endpoint → same LeashService, same zones.

## 6. Upgrade path — UWB precision leash (uses the iPhone 15 Pro's U2)

For a *precise* leash and the foundation of real follow-me:

- **Hardware:** a Qorvo DW3000-based UWB module on the dog (e.g. an ESP32+DW3000
  board or a DW3000 breakout wired to the BiBoard's Grove UART, pins 9/10);
  ~$30–50, a few grams — within the Bittle's payload.
- **Protocol:** the module must speak **Apple's Nearby Interaction accessory
  protocol** (FiRa-based; Qorvo ships an NI-compatible reference stack for
  DW3000). The iPhone side is the NI framework in a small app — so this path
  *does* require phone software, and NI sessions need the app foregrounded
  (screen on) per Apple's rules.
- **What it buys:** ±10–30 cm true distance (vs "half to double" RSSI bands) up
  to ~25–50 m, plus bearing when the U2's AoA conditions are met — enough to make
  leash length exact and to steer follow-me. Session start also needs a BLE
  side-channel to exchange NI tokens (the existing `<ID>_BLE` UART can carry it).
- **Integration:** the NI app replaces the RSSI source; distance feeds the same
  LeashService zone machine (now with honest meters), bindings unchanged.
- Sequencing: only after the away-mode leash proves out; it's a hardware +
  firmware + app project and deserves its own brief when it comes up.

---

## 7. Constraints respected

- **2-client WS cap:** untouched — leash telemetry rides the adapter's existing
  single WS connection.
- **Arbiter ownership:** leash reactions are ordinary behaviors at their stated
  priorities; `leash.lost` (safety) sits beside low-battery rest. The firmware
  dead-man is deliberately *below* the framework — it only acts when the host is
  provably gone, the one case the arbiter cannot cover.
- **Voltage gating, driver rules:** inherited — reactions are stored behaviors
  run by the existing executor.
- **No new robot-side network surface:** still exactly one WS on :81 (plus the
  BLE advertisement it always broadcast).

## 8. Phasing

- **Phase 0 — feasibility spike (one evening):** enable Maximize Compatibility,
  join dog + laptop to the iPhone hotspot, run the stack, confirm the WS behaves
  over the hotspot. Flash a debug build printing `WiFi.RSSI()` (or just add the
  `event_rssi` frame straight away — it's ~20 lines); walk the leash boundary
  and log RSSI. *Kill criterion:* boundary RSSI indistinguishable from at-heel
  noise → fall back to BLE app (§5) or UWB (§6).
- **Phase 1 — firmware:** `event_rssi` frame, multi-SSID credentials, dead-man
  rest flag. Flash + validate per the usual runbook.
- **Phase 2 — adapter LeashService:** unsolicited-frame reading (`event_rssi` —
  this also opens the door for `EXCEPTION_REPORT`/battery events from the
  behavior brief's Phase 3), smoothing, zone machine, zone events into bindings;
  orchestrator proxy + STOMP; GUI leash widget with live RSSI/zone, thresholds,
  walk-test capture.
- **Phase 3 — bindings + full walk test:** seed `leash_warn`/`leash_far`/
  `leash_lost` behaviors (bark assets exist host-side), end-to-end test on a real
  walk, including a deliberate out-of-range dead-man check.
- **Later:** BLE at-home leash (§5) if wanted; UWB brief (§6) when precision or
  follow-me is on the table.

## 9. Open questions

1. Dead-man arming: explicit away-mode flag vs always-armed with generous N.
   (Lean: armed via command when leash mode starts; disarm on normal shutdown.)
2. `leash.lost` recovery: latched until human resume, or self-clearing on
   reconnection? (Lean: self-clearing to `near` + activity-log entry.)
3. Hotspot IP churn: the dog's IP on the hotspot differs from home
   (172.20.10.x); adapter needs per-network robot address config or mDNS/scan
   discovery. Small, but must be decided.
4. Does the GUI need a first-class "mode" concept (home/away) beyond the leash,
   e.g. suppressing idle-ladder behaviors on walks? (Probably yes, eventually.)

**References:** `docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md` (event/binding/arbiter
model), `docs/robot/HARDWARE.md` (transports, Grove UART pins 9/10),
`docs/robot/NETWORK_API.md` (WS :81 sole surface; `event_us` push pattern),
`opencat-esp32/src/bleUart.h:126-158` (continuous advertising, NUS UUID),
`docs/design/FIRMWARE_RESET.md` (reset doctrine; kept BLE transport; silent
machine ⇒ dead-man must be firmware-side).
