# Frontend inventory — 2026-10-21

An inventory of the console (`orchestrator/src/main/resources/static/`):
what each tab holds, where the same function appears more than once, and a
proposal to go from 13 robot tabs plus a fleet page to 7 tabs. It
complements [OVERLAP_INVENTORY_2026-10-21.md](OVERLAP_INVENTORY_2026-10-21.md)
§3.8, which covers the console's stylesheet and card duplication, and the
backend overlaps behind several of the rows here.

## 1. Safety finding

The **Behavior Lab** tab (`behavior.html`, visible in stationary mode) has a
**Start** button (`#btn-loop`) that calls `POST /behavior/start`
(`BehaviorController.java:78`) and starts the Java `RobotBehaviorLoop`. That
loop has not run since the 2026-09-25 incident. Its **Do it** button
(`POST /behavior/action/{action}`) submits a manual action through the same
loop. The overlap inventory's "no GUI button" note is wrong on this point.
Remove both buttons before anything else in §5.

## 2. What is there now

The robot page's tabs come from the `TABS` registry in `app.js`. Tabs with a
`page` are iframes (`?embedded=1`); Actions and Specs are inline in
`index.html`.

| Tab | Source | What it holds |
|---|---|---|
| *Fleet Dashboard* (sidebar) | `index.html#dashboard`, `app.js renderRobotGrid` | Grid with one card: battery bar and a 24 h sparkline |
| **Personality** | `personality.html` | 4 mode cards, plus a terminal: the `/activity` log, the conversation, and a typed input that posts `/conversation/say` |
| **Actions** | `index.html`, `cards.js` | Arbiter card (6 runs), queue card, battery saver, action feed |
| **Dashboard** | `dashboard.html` | 14 widgets (camera, sonic, minimap, battery, mic, heading, mood, radar, WiFi, navigation, motion, satellite, speaker with a "say" box, events from `/activity`), plus a "she needs help" banner |
| **Thoughts** | `mind.html` | Arbiter card again (12 runs, with "why"), "Agent thoughts" (`/behavior/history`), conversation card (full) |
| **Map** | `map.html` | Map, navigation, sonar sweep, WiFi sniff, errors, the same "she needs help" prompt, pose card, collection points |
| **Leash** | `leash.html` | WiFi signal chart, signal source, thresholds, walk-test marks |
| **Metrics** | `metrics.html` | Orchestrator metrics, recent errors, per-robot tiles |
| **Specs** | `index.html`, `specs.js` | Polling settings and static hardware specs |
| **Control** (stationary) | `control.html`, `control.js` | Balance/Rest, servos, skill buttons, a "live readings" strip, mood card |
| **Behavior** (stationary) | `behavior.html`, `behavior.js` | Loop Start, personality chart, Pet/Call/Play, "Do it", action frequency, personality decisions, **plus** startup greeting and idle ladder |
| **Audio input** | `ears.html` | Mic level, phrase recorder, vocabulary, transcripts |
| **Audio output** | `voice.html` | Speaker card with a "say" box, conversation card (compact) |
| **Vision** | `eyes.html` | Camera, range |

Also in the static directory but unlisted: `builder.html` / `builder.js`
(Sequence Builder, "pending its rebirth as a behavior builder").

## 3. Overlap

| Function | Appears in |
|---|---|
| Typing to her (LLM, then speaker) | Personality terminal, Thoughts conversation card, Audio output conversation card: 3 copies, all posting `/conversation/say` |
| Speaking text exactly (no LLM, `/mouth/say`) | Dashboard speaker widget, Audio output speaker card. It sits next to the conversation input and looks the same but behaves differently. |
| "What is she doing" | Arbiter card on Actions *and* Thoughts. The action feed (Actions) and the `/activity` log (Personality terminal, Dashboard events widget) show the same lifecycle notes. |
| "She needs help" prompt (`/navigation/errors/respond`) | Dashboard banner *and* Map panel, same three buttons |
| Live sensor readings | Dashboard widgets, Control "live readings" strip (`hlSensesStrip`), and each sense's own tab |
| Mood light | Dashboard widget, Control mood card |
| Battery | Fleet card and sparkline, Dashboard widget, battery saver on Actions |
| WiFi location | Map (sniff, samples) and Leash (signal, thresholds) |
| Status chips | Mode chip on the robot header, Personality and Control. Clock on the header and on Personality. |
| The name "Dashboard" | Fleet page and the per-robot tab |
| Diagnostics | Sidebar health and transport widgets, Metrics, Specs |

## 4. Dead or broken

- **Panels backed by the retired Java loop:**
  - Thoughts "Agent thoughts" (its empty state says "start the loop in the Behavior tab")
  - Behavior Lab's personality chart, Interact buttons, action frequency and personality decisions
- **Dashboard wrench buttons that land in the wrong place** (`dashboard.html` `WIDGETS`):
  - Events → `activity`, a tab that doesn't exist, so it silently falls back to Personality.
  - Battery → `mind` (Thoughts), but the battery saver is on Actions.
  - Mood → `control` and Motion → `behavior`, both hidden outside stationary mode.
- **Leftover files:** `builder.html` and `builder.js` are still in the JAR but unlisted.

## 5. Proposal: 7 tabs

| New tab | Built from | Notes |
|---|---|---|
| **Home** | Fleet Dashboard + Dashboard tab + robot header | Open straight on Laika; drop the one-card fleet grid. Show "she needs help" as **one global banner** on every tab, and delete the Map copy. |
| **Talk** | Personality + Thoughts conversation + Audio output | Mode picker on top, then **one** console: transcript, a typed question, and a "speak verbatim" toggle (or a `/say` prefix) in place of the separate speaker box. Voice and reply-cap settings go in a small side panel. |
| **Activity** | Actions + Thoughts arbiter card | One arbiter card with "why", the queue and the feed. Point everything at the action feed, which lets `/activity` be retired (overlap inventory §3.1). |
| **Map** | Map + Leash | Leash becomes a "Signal" panel. Both are WiFi position sensing and already share the sniff and sample data. |
| **Senses** | Vision + Audio input | Camera and range, mic, transcripts and vocabulary, as two columns or sub-sections. |
| **Workshop** (stationary) | Control + the live half of Behavior | Servos, skills, Balance/Rest, mood light, startup greeting, idle ladder. Delete the "live readings" strip (Home has them). |
| **System** | Metrics + Specs + sidebar widgets | Polling settings, health, transport, metrics, hardware specs. |

**To delete outright:** the Behavior Lab loop controls and personality
panels, Thoughts "Agent thoughts", `builder.html` / `builder.js`, the
duplicate mode and clock chips, and the robot dropdowns, which only matter
with more than one robot.

## 6. Suggested order

1. **Delete the dead panels**, starting with the loop Start and Do it buttons
   (§1). This needs no layout decisions and removes most of Thoughts and
   Behavior Lab.
2. **Merge Talk.** This is the biggest single simplification: four chat and
   say inputs become one.
3. **Merge Activity** and retire `/activity`. This is step 2 of the overlap
   inventory's consolidation order.
4. **Make "she needs help" a global banner** and fix the wrench targets.
5. **Merge the remaining tabs** (Map + Leash, Senses, Workshop, System) and
   unify the three stylesheets (overlap inventory step 6). This step is
   mostly moving markup around.
