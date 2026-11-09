# Running a demo away from home (hotspot, no home WiFi)

How to get Laika and the orchestrator stack running on a different network
— a venue, a phone hotspot, a different laptop — instead of the home
router. Written up after planning a MacBook-Air-as-host demo; see
`orchestrator/docs/design/ARRIVAL_DAY_RUNBOOK.md` §4c for the one time
this was done before (an iPhone-hotspot "leash walk").

## The short version

1. Prep everything at home, on real internet, before you leave.
2. Reconfigure Laika's WiFi over USB serial to join the hotspot.
3. Point `.env` at her new IP and start the stack on the laptop that's
   joined the same hotspot.
4. Drive her from the GUI like normal.

The satellite board (camera/mic/LED) is **not part of this** — see below.

## What you need

- A laptop with Docker installed, and this repo cloned on it.
- A hotspot Laika, the laptop, and (if you want to view the GUI from a
  second device) your phone can all join.
- A USB cable to Laika's BiBoard and a serial terminal (Arduino IDE's
  Serial Monitor, `screen /dev/tty.usbserial-XXXX 115200` on Mac/Linux,
  PuTTY on Windows — 115200 baud).
- Laika safely on her mount for the WiFi reconfig step (a power cycle is
  involved).

## 1. Prep at home, before you travel

Run the full stack once on your normal home network and confirm it comes
up clean:

```
docker compose build
docker compose up -d
```

Do this **before** you leave, with real internet available. A venue
hotspot may have no internet uplink at all (see the hotspot note below),
so every image Docker needs — the orchestrator, the Python adapters,
Postgres, and Ollama's base image plus whatever model it pulls if you want
voice/conversation in the demo — has to already be cached locally. Treat a
failed `docker compose up -d` at the venue as a packing mistake, not
something to debug on site.

## 2. Choose the hotspot

You need a WiFi network that both Laika and the laptop running Docker can
join.

- **Phone hotspot (simplest, most reliable).** Phones are built to serve
  WiFi while also having their own uplink; just join it from the laptop.
- **Laptop creates its own network.** A MacBook with a single WiFi radio
  can't use WiFi for internet *and* broadcast its own WiFi hotspot at the
  same time — Internet Sharing shares an *other* connection (Ethernet) out
  over WiFi, it can't share WiFi-to-WiFi on one antenna. What it *can* do
  is create an isolated ad-hoc network with no internet uplink at all
  (macOS Wi-Fi settings, "Create Network", if your version still exposes
  it). That's fine for Laika — she only needs LAN access to the laptop,
  not real internet — but only if step 1's prep actually ran clean, since
  this network has zero internet of its own.

Either way: **Laika does not need internet**, only a LAN path to whatever
machine is running `docker compose`. Only Ollama's model pull (first run)
and live Anthropic API calls (voice/conversation) need real internet, and
both should already be handled by prepping at home first.

## 3. Reconfigure Laika's WiFi (serial, every time the network changes)

The BiBoard has no GUI WiFi picker. Credentials live in two firmware
slots, written over USB serial. The primary-slot write tool is unreliable
(per the runbook), so use the secondary slot:

1. Connect Laika to a laptop over USB, open a serial terminal at 115200
   baud.
2. Send: `XW2%<hotspot-SSID>%<hotspot-password>`
3. Power-cycle her.
4. Watch the serial log for `WiFi: <ip>` — that's her new IP. Boot tries
   the primary slot first and can take ~25s to fail over to the one you
   just wrote, so give it a moment.

Write down that IP; it goes in `.env` in the next step. (If you ever
switch back to home WiFi, repeat this with the home SSID/password to
restore her secondary slot.)

## 4. Point `.env` at the new network

If you don't already have `orchestrator/.env`, copy it from
`orchestrator/.env.example`. Then set:

- `BITTLE_WIFI_HOST` — the IP you just read off serial.
- `SATELLITE_HOST` — leave **blank** (see below).
- `MOCK_MODE=False`, `ULTRASONIC_PIN=9` — same as the home setup.
- `ANTHROPIC_API_KEY` — only if voice/conversation is part of this demo.

Keep a copy of your home values (`BITTLE_WIFI_HOST`, `SATELLITE_HOST`)
somewhere before overwriting them — you'll want them back afterward.

## 5. The satellite board (camera/mic/LED) — skip it

The XIAO satellite's WiFi SSID, password, *and* the adapter's IP are
hardcoded in `satellite/xiao_sense/secrets.h` at **compile time** — there
is no runtime config for it. Moving networks means editing that file and
reflashing over Arduino IDE, which isn't a realistic on-site fix.

Leaving `SATELLITE_HOST` empty means the Camera card shows "no camera
configured" and the camera/mic/LED sense toggles report unavailable — the
GUI already handles this gracefully (it's the same path Mocha, the
camera-less mock fixture, always runs). Everything else — Scan, Walk,
Posture, Debug (sit/stand/lay/bark) — works independently of the
satellite.

## 6. Start the stack and drive her

```
docker compose up -d
```

Open `http://localhost:8080` on the laptop, or `http://<laptop-lan-ip>:8080`
from any other device on the same hotspot (your phone, to walk around
while watching her). From the GUI:

- **Driver** card: leave it on Manual (it's disabled/fixed to Manual as of
  this repo's current state).
- **Debug** card: Play positive bark / Sit / Stand / Lay down.
- **Scan** card: Update to sweep, click a point on the dial to pin a
  target, Walk to send her there.

## Coming home

Repeat step 3 with your home WiFi's SSID/password to put her back on the
router, and switch `.env` back to the home `BITTLE_WIFI_HOST`/
`SATELLITE_HOST` values.
