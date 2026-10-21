# Overlap inventory and post-merge review — 2026-10-21

Written after fast-forwarding `main` onto `feat/introduce-yourself`
(`20f8ec3..d878b74`, 5 commits: introduction text, Actions tab, Kokoro TTS,
mode-log dedupe, terminal console). `main` had no commits of its own past the
merge base, so there were no conflicts. Both suites were green before and
after the follow-up fixes below (adapter 361 passed / 2 skipped, orchestrator
113 passed).

Where this repeats [AUDIT_2026-09-02.md](AUDIT_2026-09-02.md), the audit is
cited rather than restated; most of its fix #11 ("delete the deprecated brain
and legacy endpoints") is still open and accounts for a large share of the
overlap below.

## 1. Fixed in the working tree (uncommitted)

| # | Where | Problem | Fix |
|---|---|---|---|
| F1 | `static/style.css`, `static/personality.html` | The queue card moved from Personality to the Actions tab (`index.html`), but its `.qs-*` / `.pill` / `.status-*` CSS stayed in `personality.html`. On the Actions tab it rendered unstyled; on Personality the CSS was dead. | Rules moved to `style.css` (mapped onto its tokens), dead copy removed. |
| F2 | `RobotController.actionFeed`, `GetActionFeedUseCase`, `RobotAdapterPort`, `PythonAdapterHttpClient`, `BroadcastActionFeedUseCase` | The console asks for `/actions/feed?limit=60` (Actions tab) and `?limit=12` (queue card), but the Java proxy dropped the query string and the 1 s broadcast used the adapter default of **20**. Now that speech and every lifecycle note share the feed, the 40-line Actions list never filled past 20. | `limit` (default 20) threads through to the adapter; the broadcast sends 40. New controller test; `openapi.json` regenerated. |
| F3 | `dog/app/app.py` `log_activity` | Since `log_activity` started mirroring into the action feed, `/mouth/say` and `/mouth/play` showed every utterance twice: the mouth's own `SPEECH`/`SOUND` entry and a `VOICE "Said: …"` / `"Played sound: …"` note. | `log_activity(..., feed=False)` for those two routes. Activity list is unchanged. Regression test in `test_voice_api.py`. |
| F4 | `static/personality.html` `refreshLog` | **Pre-existing:** `/activity` is newest-first, but the console took `.slice(-40)`, which is the 40 *oldest* entries. Once the log passed 40 lines, new activity stopped appearing in the terminal (or appeared ~60 entries late). | `.slice(0, 40)`. |
| F5 | `static/cards.js` introduction editor | The console accepts up to 2000 characters, but `cap_reply` cuts a spoken answer at `CONVERSATION_REPLY_CHARS` (320). The adapter's `truncated` flag is never shown, because the orchestrator's own `GET /conversation/introduction` shadows the adapter route at the same path. So a long introduction saved "fine" and was silently cut short when spoken. | The save confirmation now warns when the text is longer than the reply cap shown in the same card. |

## 2. Other findings, not changed

- **Adapter restart loses pushed state.** Mode and introduction are both
  pushed once at *orchestrator* boot (`FleetInitializer`). If only the adapter
  container restarts, she falls back to `stationary` and
  `DEFAULT_INTRODUCTION` until the orchestrator restarts or someone re-saves.
  For mode that fallback is the safe one; for the introduction it is a
  silent revert. The fix is to resync when an adapter goes from offline to
  online. Nothing tracks that transition today: the 4 s status broadcast polls
  each adapter, but it doesn't remember the previous state and only runs
  while a console is connected.
- **Mode list is defined five times and they disagree.** `OperatingMode` (Java,
  4 modes), `mode.py MODES` (4), the `app.py /mode` route (hard-coded 3,
  rejects `phone`), `personality.html MODES`, and `app.js TABS[].modes`. Selecting
  Phone gets a 400 from the adapter. That is probably intended while Phone is
  a stub, but it is enforced by accident in the route, not by `mode.py`.
- **Motion classification is defined four times.** `bittle_controller._is_motion`
  (deny-list), `poll_policy._MOTION_PREFIXES` (allow-list incl. `L`),
  `sensor_log.classify` (no `L`; counts `kwkF` without a step count as an advance),
  `senses._ADVANCE/_TURN` regexes (require a step count). They disagree at the
  edges.
- **`/voice/health` is stale:** `ttsConfigured` only checks Eleven Labs and the
  speaker is reported as "stubbed". Kokoro or espeak-ng is what actually speaks
  now (`mouth.tts_engine_name`).
- **Kokoro packaging is implicit:** `dog/Dockerfile` does `COPY . .`, so the
  ~190 MB model is baked into the image only if `tools/download_kokoro.py` ran
  before the build. Otherwise the container quietly falls back to espeak-ng.
  This works as designed but isn't documented next to the Dockerfile.
- `_load_kokoro()` isn't guarded by a lock. Two concurrent first utterances
  would load the model twice. Harmless, just slow.
- `audioop` (used by `mouth.py`) is removed in Python 3.13. The image pins
  3.11, so this only matters at the next base-image bump.
- The arbiter bypasses (`/command`, `/servo`, `/choreography/execute`,
  `/execute_action`, gait learner) and the Java behavior loop
  (`POST /behavior/start` is still unguarded, with no GUI button) are as described
  in the audit. They are unchanged.

## 3. Overlap inventory

Each row is one function implemented in more than one place. **Keep** marks
the copy that the current design (CLAUDE.md, the briefs) treats as
authoritative.

### 3.1 "What she did": six logs

| Record | Grain | Storage | Read by |
|---|---|---|---|
| `action_feed.py` ActionFeed | arbiter step + speech + lifecycle note | memory, 200 | Actions tab, queue card (**keep**: the console's single source since this merge) |
| `app.py _activity_log` | free-text lifecycle line | memory, 100 | Personality terminal, Dashboard "events" widget, `BroadcastActivityUseCase` (5 s sweep, **no subscriber left** after this merge) |
| `sensor_log.ActionLog` | every motion command reaching firmware, with sensor snapshot and outcome | SQLite | `/navigation/data/export` (ML/mapping) |
| `behavior_store` run log | one arbiter submission | SQLite | arbiter card, Thoughts |
| `DecisionHistoryRepositoryAdapter` (Java) | one behavior-loop decision | Postgres | Thoughts "history" (loop no longer runs) |
| `conversation_turns` | one voice/typed turn | SQLite | conversation card, Personality terminal |

Recommendation: retire `_activity_log`. Point the Personality terminal and
the Dashboard events widget at the action feed (which now carries every
lifecycle note), then delete `BroadcastActivityUseCase`, `GetRobotActivityUseCase`,
`ActivityLog`, and `/activity`. `ActionFeed` and `ActionLog` record the same
commands at different layers: arbiter step vs. wire command. That split is
deliberate (live view vs. dataset), but it is worth saying so in
`action_feed.py`'s docstring.

### 3.2 Talking to her: three entry points and three speech paths

| Function | Implementations |
|---|---|
| Typed question → LLM → speaker | Personality terminal (`personality.html`), conversation card on **Thoughts** (`mind.html`, full), conversation card on **Audio output** (`voice.html`, compact). All three post `/conversation/say`. |
| Text → speaker, no LLM | speaker card (`/mouth/say`) on Audio output and Dashboard. |
| Legacy voice chain | `/voice/demo` (stubbed wake/record, buzzer, Eleven Labs MP3 to `/static/responses`) and `/voice/speak`. No GUI caller. |
| TTS | `mouth.default_tts` (Eleven Labs → Kokoro → espeak-ng → tone, to the speaker) vs `voice.synthesize_speech` (Eleven Labs only, to an MP3 file). |
| "Feedback sound" | `/sound` buzzer patterns (`voice.BEEP_PATTERNS`), `/mouth/play` clip library, `conversation._bark`. |
| Persona text | `conversation.DEFAULT_PROMPT`, `conversation.DEFAULT_INTRODUCTION` (+ Postgres copy), `voice.LAIKA_SYSTEM_PROMPT`, `personality_engine.SYSTEM_PROMPT` ("the mind of **Bittle**"), `mouth.PREVIEW_TEXT`, `_display_content` ("Hello! I'm **Bittle**"). |

Recommendation: keep `conversation.py` + `mouth.py` and delete the `voice.py`
demo chain (`/voice/demo`, `/voice/speak`, `synthesize_speech`'s MP3 path,
`RunVoiceDemoUseCase`). Keep `query_ollama` and `ollama_health`; they are the
live LLM client. Decide on one typed-chat surface: the Personality terminal
and the Thoughts card are the same feature twice.

### 3.3 Deciding what to do: four brains

| Brain | Where | Status |
|---|---|---|
| Adapter `AutonomousLoop` + `personality_engine.py` (Ollama/Claude/mock) | `app.py`, `/autonomous/*`, `/behavior`, `/interact` | deprecated (audit fix #11) |
| Orchestrator `RobotBehaviorLoop` + `RuleBasedDecisionEngine` → `/execute_action` | Java `application.service` | never started since the 2026-09-25 incident; still reachable via `POST /behavior/start` |
| Mode-driven generators: `explorer.py`, `fruitfly_drive.py`, `event_binder` idle ladder | adapter, through the arbiter | **keep**: the live design |
| Conversation router (LLM picks a tool) | `conversation.py` | **keep** |

Personality state also exists twice: the adapter's `Personality` table
(energy/happiness/boredom/curiosity, broadcast every 10 s on
`/topic/robot/{id}/personality`, stored by `app.js` and never rendered) and
the orchestrator's `PersonalityState` (Postgres, `/behavior/personality`). The
"Personality" tab itself shows neither; it shows operating modes.

### 3.4 Executing motion: five doors, one of which is the arbiter

`/arbiter/invoke` (**keep**), `/command`, `/servo`, `/choreography/execute`
(`ChoreographyLibrary`, which overlaps the behavior store's skills), and
`/execute_action` (`action_executor.py`, the Java loop's vocabulary). Java
mirrors these as `SendRobotCommandUseCase`, `MoveServosUseCase`,
`ExecuteAnimationUseCase`, `ExecuteRobotActionUseCase`, `SubmitManualActionUseCase`,
and `InteractWithRobotUseCase`. There are also two action catalogs: Java `ActionCatalog`
(behavior-loop actions) and the `ActionRegistry` endpoint (`/api/actions`,
voice/GUI metadata).

### 3.5 Per-robot "pushed setting" stack, done twice

Mode and introduction are the same pattern line for line: domain record,
JPA entity/repo/adapter, port, Get/Set use cases, Resync use case, controller,
`FleetInitializer` hook, and an in-memory mirror on the adapter. The only
real differences are ordering (mode posts before saving so a failed push aborts;
introduction saves first so it can be edited while she's off) and validation. With
two instances, a generic `RobotSetting` isn't worth it yet. At the third
(voice choice and reply cap are the obvious candidates, currently adapter
`settings` rows), extract one resync over a key/value table.

### 3.6 Orchestrator → adapter plumbing

`RobotController` has 88 routes; 67 go through the four generic relays
(`RelayGet/Post/PostWithBody/GetBinary`). About ten more are typed one-liners
that do the same thing with a record. Each one costs a port method, an HTTP-client
method, a use case and a `RobotControllerTest` mock: `GetActionFeed`,
`GetRobotActivity`, `GetFruitflyStatus`, `GetServoState`, `GetRobotDisplay`,
`GetRobotPersonality`, `GetRobotCapabilities`, `GetVoiceHealth`,
`GetRobotAutonomousStatus`, `PlaySound`. Several of them are already on the
deprecated list. New pass-through routes should use the relay.

### 3.7 Observing the controller: four wrappers and three clocks

`controller.send_command` is monkey-patched in a chain by `senses.instrument`
(odometry), `navigation.instrument` (ActionLog), `metrics` (timing) and
`_observe_for_poll_policy`. Order matters and lives only in `app.py` import
order. "Last motion" is tracked three times: `controller.last_motion_at`,
`arbiter.last_motion_at`, and `navigator._last_motion_at`. A single
`controller.on_command(listener)` hook plus one shared `classify()` would
replace the wrappers and the four classifiers in §2.

### 3.8 Console

- Three stylesheets for one palette: `style.css` (shell), `console.css`
  (tabs; says it "matches personality.html"), and `personality.html`'s own
  `:root` tokens with different names for the same colours. F1 had to translate
  between them.
- The arbiter card is mounted on both Actions ("Current behavior", 6 runs) and
  Thoughts ("What I'm doing, and why", 12 runs).
- The queue card and `app.js` each open their own subscription to
  `/topic/robot/{id}/actions` on the Actions tab (two STOMP clients).
- Two "say something" cards (speaker card vs conversation card) sit side by
  side on Audio output with similar input boxes and different behaviour.

### 3.9 Docs

`dog/docs/SPRING_BOOT_ORCHESTRATOR_SETUP.md` (1560 lines) and
`PYTHON_FLASK_JAVA_INTEGRATION.md` predate `ARCHITECTURE.md`, which is the
authoritative source. `PERSONALITY_SYSTEM_DESIGN.md` describes the
orchestrator personality loop that no longer runs. These are candidates for
`archive/`.

## 4. Suggested consolidation order

1. Audit fix #11 (deprecated brain + legacy routes + personality/display
   sweep): this removes most of §3.3, half of §3.4 and several §3.6 one-liners.
2. Retire `_activity_log` (§3.1). The feed already carries everything.
3. Delete the `voice.py` demo chain and pick one typed-chat surface (§3.2).
4. Resync mode and introduction when the adapter comes back online (§2).
5. One command-listener hook and one `classify()` (§3.7).
6. Unify the console palette tokens (§3.8).
