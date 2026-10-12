# GUI inventory snapshot

| | |
|---|---|
| **Generated** | 2026-10-12T08:31Z |
| **From** | `development` @ `35898b38d0437b994323f0c47ec475ee5437122e` (last GUI change: `983705f`, AGENT-18) |
| **Ticket** | #48. Report only: no code was changed. Regenerate by reopening #48 with `status:to-do`. |
| **Scope** | GUI = `orchestrator/src/main/resources/static/` (13 pages, ~7,600 lines). Backend = the orchestrator's controllers, `docs/api/openapi.json` and STOMP publishers. |

**Method.** The tab registry, page scripts and shared cards were read by hand. The REST routes come from the `@*Mapping` annotations and were compared with `openapi.json`. The GUI's calls were extracted from `fetch`/`hlApi`/`api`/`post` helpers and `<img src>` URLs. Each "unused" claim in §3 was confirmed with a grep across all static files.

## At a glance

- **1 console shell + 13 robot tabs**, plus 1 unlisted page (`builder.html`). Every tab page except Activity and Specs also works as a standalone page.
- **Backend: 106 REST operations**, and the OpenAPI spec and controllers agree exactly (no drift). There are **9 STOMP topic families**, all server→client.
- **The GUI uses 80 of the 106 operations. 26 are never called**, and 9 of those are marked deprecated.
- **3 STOMP topics and 1 polled endpoint are received and stored but never read**: `personality`, `display`, `fleet/stats`.
- **The same functions are rendered in several places.** Conversation appears in 3 places, the arbiter and the camera in 3, range/battery/leash in 3–4, and the map in 2. There are **5 different ways to make the dog do something** (§5).
- **The modes don't match the target profiles.** The backend has `stationary`, `roaming`, `fruitfly` and `phone`, and the GUI gates tabs on stationary/roaming only. The target profiles (stationary, roaming, **assistant**) have no "assistant" mode anywhere yet.

---

## 1. Tab-and-control inventory

### 1.0 Shell: `index.html` + `app.js`

The sidebar holds Dashboard, one entry per robot (`GET /api/fleet/robots`) and two widgets: **Orchestrator** (`GET /api/health`) and **Transport** (STOMP connection state).

- **Fleet dashboard** (`#page-dashboard`): one card per robot showing status and a battery sparkline. Data comes from `GET /api/fleet/status`, `GET /api/fleet/stats` (poll fallback), STOMP `/topic/fleet/status`, `/topic/robot/{id}/status` and `GET /api/metrics/history?robotId=&limit=24`. Clicking a card opens the robot page.
- **Robot page header:** chips for connection, mood, mode, uptime and the browser clock. Data comes from STOMP `status`/`mode` and `GET …/mode`.
- **Tab bar:** generated from `TABS` (`app.js:293`). A tab is shown if it's `always`, or if its `modes` list contains the current mode. Every tab except Activity and Specs is an `<iframe>` of its page with `?embedded=1`.

| Tab (label) | id | Page | Shown in modes |
|---|---|---|---|
| Personality | personality | personality.html | all |
| Activity | activity | (inline) | all |
| Dashboard | senses | dashboard.html | all |
| Mind | mind | mind.html | all |
| Map | map | map.html | all |
| Leash | leash | leash.html | all |
| Metrics | metrics | metrics.html | all |
| Specs | specs | (inline) | all |
| Control | control | control.html | stationary |
| Behavior | behavior | behavior.html | stationary |
| Audio input | ears | ears.html | stationary, roaming |
| Audio output | voice | voice.html | stationary, roaming |
| Vision | eyes | eyes.html | stationary, roaming |

`…` below stands for `/api/robots/{robotId}`.

### 1.1 Personality: `personality.html`
| Control / panel | What it does | Backend |
|---|---|---|
| Mode cards: Stationary Assistant, Roaming Assistant, Fruitfly, Phone (`MODES`, :183) | Shows the current mode and switches it. Fruitfly and Phone are flagged `built:false`. | `GET …/mode`, `POST …/mode/{mode}` |
| Animated mode icons, clock | Decoration | none |
| Log | Merged activity and conversation feed (polled every 2 s) | `GET …/activity`, `GET …/conversation?limit=15` |
| `term-input` + `term-send` (SEND) | Typed message to the dog | `POST …/conversation/say` |

### 1.2 Activity (inline in `index.html`)
| Control / panel | What it does | Backend |
|---|---|---|
| Arbiter card (`hlArbiterCard`) | What's running now and recent runs; **Stop** | `GET …/arbiter/status`, `POST …/arbiter/stop` |
| Power card (`hlPowerCard`) | Battery-saver tier and reasons; **Auto / Wake / Eco / Doze**; threshold fields + **Save** | `GET …/power/saver`, `POST …/power/saver`, `POST …/power/saver/config` |
| Activity feed + age | Live event list | `GET …/activity`, STOMP `/topic/robot/{id}/activity` |
| (badge palette) | LED colours for badges | `GET …/mood` |

### 1.3 Dashboard (tab id `senses`): `dashboard.html`
This is a customisable widget grid (`WIDGETS`, :162). The page controls are **Edit layout**, a **live** checkbox and **Reset layout**, plus battery colour thresholds `batt-red`/`batt-blink`. All of these are stored in browser `localStorage` only. Each widget has a **wrench** button that jumps to its "home" tab.
| Widget | Shows / controls | Backend | Wrench → tab |
|---|---|---|---|
| Camera | Live frame (every 330 ms) + play/pause | `GET …/eyes/snap` (img), `GET …/eyes`, `POST …/eyes/config` | eyes |
| Sonic | Range reading | `GET …/senses/range` | map |
| Map (minimap) | Occupancy grid | `GET …/navigation/map` | map |
| Battery | Voltage, %, saver tier | `GET …/status`, `GET …/power/saver`, `GET …/power` | mind |
| Microphone | Level, listening state | `GET …/ears` | ears |
| Heading | Dead-reckoned heading (`pose`) | via `GET …/navigation` (same poll as Navigation) | map |
| Mood | LED mood | `GET …/mood` | control |
| Radar | Last head sweep (`lastSweep`) | via `GET …/navigation` (same poll) | map |
| WiFi | Leash signal + satellite | `GET …/leash`, `GET …/satellite`, `GET …/senses` | leash |
| Navigation | Route state + error-response buttons | `GET …/navigation`, `POST …/navigation/errors/respond` | map |
| Motion | Current behavior | `GET …/arbiter/status`, `GET …/status` | behavior |
| Satellite | Satellite board state | `GET …/satellite` | eyes |
| Speaker | Speaker state + `say-text`/`say-go` | `GET …/mouth`, `POST …/mouth/say` | voice |
| Events | Activity list | `GET …/activity` | activity |

### 1.4 Mind: `mind.html`
| Control / panel | What it does | Backend |
|---|---|---|
| "What I'm doing, and why" (`hlArbiterCard`, why=true, 12 runs) | Arbiter state, cause chain, **Stop** | `GET …/arbiter/status`, `POST …/arbiter/stop` |
| Learned patterns (`hlLearnedPatternsCard`) | This mode's tools and the learned success rate per goal | `GET /api/v1/agent/{id}/tools`, `GET /api/v1/agent/{id}/patterns?goal=`, STOMP `/topic/robot/{id}/learned-patterns` |
| Agent thoughts | Last 10 decisions of the personality loop | `GET …/behavior/history?limit=10` |

### 1.5 Map: `map.html`
| Control / panel | What it does | Backend |
|---|---|---|
| `live`, **Refresh** | Poll toggle / reload | (re-runs the GETs below) |
| `navmode` checkbox | Click-on-map-to-go | `POST …/navigation/target` |
| **Sniff** | One WiFi scan now (blocks the dog ~2 s) | `POST …/senses/sniff` |
| **Re-anchor** (`reset`) | Reset the dead-reckoned origin | `POST …/senses/pose/reset` |
| Trail filters: `window`, `since`, `until`, `source`, `minAps`, `every`, `limit`, `colorBy` | Filter the fingerprint trail | `GET …/senses/samples?…` |
| Layers: occupancy, route, trail, grid, points | Display toggles | none (client-side) |
| Points layer + photos | Collection points | `GET …/collection_points?limit=300`, `GET …/collection_points/{id}/photo` (img) |
| Pose card (`hlPoseCard`) | Where she thinks she is | `GET …/senses` |
| Navigation: **Cancel**, **Sweep**, **Clear map** | Route / head scan / forget the grid | `POST …/navigation/cancel`, `POST …/navigation/sweep`, `POST …/navigation/map/reset` |
| `avoid`, `stopCm` | Obstacle avoidance on/off, stop distance | `POST …/navigation/config` |
| `override` + go | Run a skill with avoidance suspended | `POST …/navigation/override` |
| Error cards (`note`, primary buttons) | Answer navigation errors | `GET …/navigation/errors?limit=8`, `POST …/navigation/errors/respond` |
| Status | Route, map | `GET …/navigation`, `GET …/navigation/map` |

### 1.6 Leash: `leash.html` (base `…/leash`)
| Control / panel | What it does | Backend |
|---|---|---|
| State view | Signal, zone, samples | `GET …/leash` |
| `toggle` | Enable / disable the leash | `POST …/leash/config` `{enabled}` |
| `mode`, `beaconSsid` | Signal source: router or phone hotspot | `POST …/leash/config` |
| `warnDbm`, `farDbm`, `lostDbm`, `hysteresisDb`, `dwellS`, `deadManS` + **Save thresholds** | Thresholds | `POST …/leash/config` |
| `markLabel` + **Mark current signal** | Walk-test marks | `POST …/leash/mark` |

### 1.7 Metrics: `metrics.html`
| Control / panel | What it does | Backend |
|---|---|---|
| Orchestrator tiles, per-robot tiles, recent errors, last-hour table | Read-only (polled every 5 s). It has no controls. | `GET /api/metrics` |

### 1.8 Specs (inline in `index.html` + `specs.js`)
| Control / panel | What it does | Backend |
|---|---|---|
| Polling: `poll-ttl`, `poll-batt`, `poll-mult`, `poll-postures` + **Save** | Telemetry / battery poll intervals, idle multiplier and postures | `GET …/polling`, `POST …/polling` |
| Spec sheet | Hard-coded hardware facts (`BASE_SPECS`) | none (static) |

### 1.9 Control (stationary only): `control.html` + `control.js`
| Control / panel | What it does | Backend |
|---|---|---|
| Autonomy banner | Warns when the adapter's legacy loop would block manual moves (409) | `GET …/behavior/status` |
| Servo sliders (one per joint) + read-back | Move single joints | `POST …/servo` `{joints}`, `GET …/servo` |
| **Balance**, **Rest** | Fixed postures | `POST …/command` (`kbalance`, `krest`) |
| Action buttons (from capabilities) | Skills | `GET …/capabilities`, `POST …/command` |
| Live readings (`hlSensesStrip`) | Battery, range, signal, mic, satellite | `GET …/status`, `…/senses/range`, `…/leash`, `…/ears`, `…/satellite` |
| Mood light (`hlMoodCard`) | Named moods, custom colour/effect/brightness, **Apply**, **Off** | `GET …/mood`, `POST …/mood` |

### 1.10 Behavior (stationary only): `behavior.html` + `behavior.js`
| Control / panel | What it does | Backend |
|---|---|---|
| `btn-loop` Start/Stop | Orchestrator behavior loop | `POST …/behavior/start`, `POST …/behavior/stop`, `GET …/behavior/status` |
| Personality-over-time chart | Trait history | `GET …/behavior/history?limit=…`, STOMP `/topic/robot/{id}/behavior` |
| **Pet**, **Call**, **Play** | Inject events | `POST …/behavior/event/{type}` |
| `action-select` + **Do it** | Run a named action (list hard-coded in `ACTIONS`, `behavior.js:15`) | `POST …/behavior/action/{action}` |
| Startup greeting: step rows (`st-cmd`, `st-settle`, ×), **+ Add step**, **Save**, **Run now**, enable/disable | Edit and run the greeting | `GET …/behaviors/startup_greeting`, `POST …/behaviors`, `GET …/greeting`, `POST …/greeting/{run\|enable\|disable}` |
| Idle ladder: `idle-sit-s`, `idle-rest-s`, **Save**, enable/disable | Idle → sit → rest timing | `GET …/bindings`, `POST …/bindings`, `GET …/idle`, `POST …/idle/{enable\|disable}` |

### 1.11 Audio input (stationary, roaming): `ears.html`
| Control / panel | What it does | Backend |
|---|---|---|
| Live level | Mic level, listening state | `GET …/ears` |
| Conversation card (**full**: live turn, **Listen**, **Cancel**, typed **Send**, prompt template + char cap + **Save**) | "Hey Laika" turns | `GET …/conversation`, `POST …/conversation/{say,listen,cancel,prompt}` |
| Phrase recorder: `rec-seconds`, **Record**, **Adopt** variant | Record a phrase, adopt the whisper spelling | `POST …/ears/record`, then `POST …/ears/vocabulary` |
| Vocabulary: `vocab-wake`, `vocab-phrases`, `vocab-variants` + **Save** | Wake word, phrases, accepted spellings | `POST …/ears/vocabulary` (loaded from `GET …/ears`) |
| Transcripts | Newest first | `GET …/ears/transcripts?limit=12` |

### 1.12 Audio output (stationary, roaming): `voice.html`
| Control / panel | What it does | Backend |
|---|---|---|
| Voice chain health | STT, LLM and TTS status | `GET …/voice/health` |
| Speaker card: `sc-text` + **Speak**, voice/variant/speed/pitch + **Try**, clip buttons | Text-to-speech and the clip library | `GET …/mouth`, `GET …/mouth/voices`, `POST …/mouth/say`, `POST …/mouth/voice`, `POST …/mouth/play` |
| Conversation card (**compact**) | Same card as Audio input, without the prompt editor | `GET …/conversation`, `POST …/conversation/{say,listen,cancel}` |

### 1.13 Vision (stationary, roaming): `eyes.html`
| Control / panel | What it does | Backend |
|---|---|---|
| Camera image | Live frame | `GET …/eyes/snap` (img), `GET …/eyes` |
| **Pause** (`eyes-toggle`) | Camera on/off | `POST …/eyes/config` |
| Fresh-frame button | Force a new frame | `GET …/eyes/snap?fresh=1` (img) |
| `stream-link` | Raw MJPEG link, shown once the satellite host is known | **`http://<satellite>/stream` directly; bypasses the orchestrator** |
| Range + `range-live` | Range readout | `GET …/senses/range` |
| Satellite | Satellite board state | `GET …/satellite` |

### 1.14 Unlisted: Sequence Builder (`builder.html`)
No tab links to it; `nav.js:11` says it's "unlisted pending its rebirth as a behavior builder". It can still be opened by URL.
| Control | What it does | Backend |
|---|---|---|
| **Play** / **Stop** timeline | Runs steps one by one | `POST …/execute_action`, `GET …/behavior/status` |
| Timeline inspector (`insp-dur`, Remove) | Edit steps | none |
| Library: `seq-name`, **Save**, `seq-list`, **Load**, **Delete**, **Clear** | Sequences | **none: kept in browser storage only** |
| Action palette | Available actions | `GET …/capabilities` |

---

## 2. Backend surface

### 2.1 REST (OpenAPI `v1`, 106 operations)
`openapi.json` and the controllers match one-to-one: every route is in both and nothing is missing on either side. Nine operations are marked `deprecated` ("the adapter's old brain").

| Area (tag) | Ops | Covers |
|---|---|---|
| Robot | 86 | Per-robot relay to the Python adapter: hardware (servo, command, sound, abort), senses (status, senses, sensors, range, satellite), power, polling, navigation + map + collection points, leash, behaviors/bindings/greeting/idle, arbiter, ears/conversation/mouth/voice, eyes, mood, choreography, legacy autonomy/personality/display |
| Behavior | 7 | The orchestrator-owned brain: loop start/stop/status, history, personality snapshot, events, actions |
| Fleet | 5 | Robot list, status, stats, legacy fleet autonomy |
| Agent | 3 | Tools per mode, learned patterns per goal, tool submission (AGENT-01…19) |
| Mode | 2 | Get / set the operating mode |
| Metrics | 2 | Live metrics, hourly history |
| Health | 1 | Aggregated health |

Of the 106 operations, 98 sit under `/api/robots/{robotId}`. Most of those relay to the same path on that robot's adapter, so their response bodies are untyped JSON in the spec.

### 2.2 STOMP (`/ws`, simple broker on `/topic`, no `/app` destinations)
| Topic | Publisher | GUI consumer |
|---|---|---|
| `/topic/fleet/status` | `BroadcastFleetStatusUseCase` | app.js: fleet grid, sidebar, header |
| `/topic/fleet/stats` | `BroadcastFleetStatusUseCase` | app.js stores it in `state.stats`, **never read** |
| `/topic/robot/{id}/status` | `BroadcastFleetStatusUseCase` | app.js: header, grid |
| `/topic/robot/{id}/personality` | `BroadcastPersonalityAndDisplayUseCase` (from deprecated adapter `personality`) | app.js stores it in `state.personality`, **never read** |
| `/topic/robot/{id}/display` | `BroadcastPersonalityAndDisplayUseCase` (from deprecated adapter `display`) | app.js stores it in `state.display`, **never read** |
| `/topic/robot/{id}/activity` | `BroadcastActivityUseCase` | app.js: Activity tab |
| `/topic/robot/{id}/mode` | `SetRobotModeUseCase` | app.js: mode chip + tab gating |
| `/topic/robot/{id}/behavior` | `RobotBehaviorLoop` | behavior.js: chart |
| `/topic/robot/{id}/learned-patterns` | `PatternRollupService` | learned-patterns.js (Mind tab) |

The GUI never sends over STOMP. All commands go over REST.

---

## 3. Dead wiring

### 3a. Backend operations the GUI never calls (26)
Each was grepped across all static files: no references.

| Operation | Note |
|---|---|
| `POST …/abort` | **"Stop the current motion immediately": there is no e-stop button anywhere in the GUI** |
| `POST …/mouth/stop` | No way to stop speech or playback once started |
| `GET …/mouth/sounds` | Clip list; the speaker card gets clips from `GET …/mouth` instead |
| `POST …/arbiter/invoke` | Submit a behavior to the arbiter; the GUI only reads and stops the arbiter |
| `GET …/choreography/list`, `POST …/choreography/execute/{animation}` | Animations: not reachable from the GUI |
| `POST …/sound` | Buzzer tones |
| `POST …/voice/demo` | Text-in voice chain test |
| `POST …/navigation/map/cell` | Correct one map cell |
| `GET …/navigation/data/export` | Training-data export |
| `GET …/sensors/latest`, `GET …/sensors/recent` | Sensor-loop readings; the GUI uses `…/senses` and `…/status` |
| `GET …/behaviors` | List stored behaviors (the GUI loads only `startup_greeting` by name) |
| `GET …/behavior/personality` | Orchestrator personality snapshot (the chart reads history instead) |
| `GET …/conversation/prompt` | The prompt is read from `GET …/conversation`; only the POST is used |
| `GET …/ears/vocabulary` | Vocabulary is read from `GET …/ears`; only the POST is used |
| `POST /api/v1/agent/{id}/submit-tool` | Agent tool submission (meant for Claude, not the GUI) |
| `GET …/autonomous/status`, `POST …/autonomous/start`, `POST …/autonomous/stop`, `POST /api/fleet/autonomous/start`, `POST /api/fleet/autonomous/stop` | **Deprecated.** Fleet buttons were already removed (`app.js:658`) |
| `GET …/behavior`, `GET …/display`, `GET …/personality`, `POST …/interact/{type}` | **Deprecated** (old adapter brain) |

### 3b. Data fetched or subscribed to but never used
- STOMP `/topic/robot/{id}/personality` and `/topic/robot/{id}/display`: subscribed for every robot and written to `state.personality` / `state.display` (`app.js:107`–110), but nothing reads that state. Both are fed every tick from **deprecated** adapter endpoints, so the backend polls deprecated endpoints only to feed an unused subscription.
- STOMP `/topic/fleet/stats` and `GET /api/fleet/stats` (`app.js:99`, `:238`): written to `state.stats`, never read.

### 3c. GUI elements that call nothing or lead nowhere useful
- **Sequence Builder library** (`builder.html`): Save, Load and Delete only touch browser storage, and the whole page is unlisted. Its Play uses `POST …/execute_action`, a path no listed page uses.
- **Dashboard wrench buttons → hidden tabs:** Mood → `control` and Motion → `behavior`. In roaming mode those tabs are hidden. `activateTab` then falls back to Personality without any message (`app.js:329`), so the wrench opens the wrong tab.
- **Fruitfly and Phone mode cards** (`personality.html:183`): selectable, flagged `built:false`. Selecting one leaves only the "always" tabs visible.
- **Dashboard layout and battery colour thresholds**: stored in browser `localStorage` only, so they're per-browser and never reach the backend. (This may be intended; noted for the redesign.)
- `stream-link` (Vision) points the browser straight at the satellite board (`eyes.html:149`), the only GUI link that bypasses the orchestrator. It is hidden until the satellite host is known.

---

## 4. Profile tagging

**Today's modes.** The backend `OperatingMode` has `STATIONARY`, `ROAMING`, `FRUITFLY` and `PHONE` (`OperatingMode.java:5`–8). The Mode API description and the OpenAPI `Mode` tag still describe three modes (stationary, roaming, fruitfly). The GUI's tab gating knows only `stationary` and `roaming`. The Personality page titles them "Stationary Assistant" and "Roaming Assistant".

**Target profiles.** The target profiles are stationary, roaming and **assistant**, and there is no `assistant` mode yet. For this tagging, *assistant* is read as a talk-first profile: conversation, voice, listening, mood and status, with no locomotion, mapping or manual servo work. Fruitfly and phone have no equivalent among the three targets.

`all` = useful in every profile (core or system).

| Item | Profile | Why |
|---|---|---|
| Profile/mode selector (Personality) | all | It's the organising control itself |
| Personality console (typed message) | assistant | Pure conversation |
| Activity feed | all | Universal "what happened" |
| Arbiter card (Activity, Mind) | all | What's running now + Stop |
| Battery saver card | all | Power matters everywhere; most acute when roaming |
| Fleet dashboard + robot header | all | Navigation and status |
| Dashboard widget grid | all (contents per profile) | Camera, mic, speaker, mood → stationary/assistant; map, sonic, radar, heading, navigation, WiFi → roaming |
| Mind: agent thoughts | stationary, roaming | Autonomous decision loop |
| Mind: learned patterns | stationary, roaming | Tools are mode-scoped (stationary = postural; roaming = adds walking) |
| Map: trail, layers, filters, points, photos | roaming | Mapping and exploration |
| Map: navigation (target, cancel, sweep, avoidance, override, errors) | roaming | Locomotion |
| Map: Sniff, Re-anchor | roaming | Localisation |
| Leash (all) | roaming | Only matters when she moves |
| Metrics | all (admin) | System health; not profile-specific |
| Specs: polling settings | all (admin) | Telemetry tuning |
| Specs: spec sheet | all (reference) | Static |
| Control: servo sliders, Balance/Rest, action buttons | stationary | Manual posing in place (currently gated stationary) |
| Control: live readings strip | all | Status |
| Control: mood light | stationary, assistant | Expressive, no motion |
| Behavior: loop start/stop, chart | stationary (+ roaming) | Personality loop runs regardless of profile, but it's gated stationary-only today |
| Behavior: Pet/Call/Play, Do it | stationary | Interaction in place |
| Behavior: startup greeting, idle ladder | stationary, assistant | Lifecycle behaviors while stationary |
| Audio input: level, conversation (full), recorder, vocabulary, transcripts | assistant (+ stationary) | Listening and conversation |
| Audio output: voice health, speaker, conversation (compact) | assistant (+ stationary) | Speaking |
| Vision: camera, pause, fresh frame | stationary, assistant | Watching from one spot (roaming uses it for collection-point photos via Map) |
| Vision: range, satellite | roaming (+ stationary) | Obstacle sensing |
| Sequence Builder (unlisted) | stationary | Choreography in place |

---

## 5. Observations (facts, no fixes)

**Duplicated surfaces (same data/control in several places)**
- **Conversation**: Audio input (full card, `ears.html:273`), Audio output (compact card, `voice.html:56`), Personality console (`personality.html`, posts the same `…/conversation/say`).
- **Arbiter / "what's she doing"**: Activity tab (`app.js:438`), Mind tab (`mind.html:72`, with cause chain), Dashboard Motion widget.
- **Camera**: Vision tab and Dashboard Camera widget, each polling `…/eyes/snap` (the dashboard every 330 ms).
- **Range**: Vision, Dashboard Sonic, Control live-readings strip.
- **Leash / WiFi signal**: Leash tab, Dashboard WiFi widget, live-readings strip.
- **Battery / power**: Activity power card, Dashboard Battery widget, fleet card sparkline, live-readings strip.
- **Map**: Map tab and Dashboard minimap. Navigation error responses can be answered from both.
- **Mood light**: Control tab card and Dashboard Mood widget.

**Five ways to make the dog do something**
1. Control: `POST …/command` (skills from `GET …/capabilities`).
2. Behavior: `POST …/behavior/action/{action}` (list hard-coded in `behavior.js:15`).
3. Builder (unlisted): `POST …/execute_action`.
4. `POST …/arbiter/invoke` (not in the GUI).
5. `POST …/choreography/execute/{animation}` (not in the GUI).

**Two notions of "autonomy"**: the orchestrator's behavior loop (Behavior tab Start/Stop, `/behavior/start|stop`) and the adapter's deprecated legacy loop. Control still checks for the legacy loop because it blocks manual moves with 409 (`control.js:99`).

**Naming**
- "Dashboard" is both the fleet page (sidebar) and a robot tab (id `senses`, `app.js:296`).
- The "Personality" tab holds the mode selector and console, while the personality *traits* chart lives on the Behavior tab (stationary only).
- "Audio input" / "Audio output" are tab labels, while their ids and pages are `ears` / `voice`.

**Mode gating vs content**
- Behavior (loop control and personality chart) and Control are hidden in roaming, though the loop also runs in roaming.
- Gating has no entries for `fruitfly` / `phone`.
- Iframes for all 11 framed tabs are created up front regardless of mode (`app.js:314` comment); they load lazily on first open.

**Safety-relevant gaps**: no GUI control for `POST …/abort` (immediate stop of motion) or `POST …/mouth/stop`.

**Polling load**: the Dashboard grid alone runs 13 pollers (330 ms – 15 s) while visible. Hidden frames pause via the `laika-visible` message (`common.js` `hlVisible`).
