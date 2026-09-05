# Planning Brief — "Hey Laika" conversation (wake → listen → think → speak)

**Status:** steps 1 to 3 built 2026-09-05 (`dog/app/conversation.py`, relay routes,
console cards); step 4, tuning on the dog, and step 5 docs remain. The owner's
answers: keyword motion shortcuts stay; neutral assistant prompt by default;
five to eight seconds of wait is acceptable with the LED as the spinner;
espeak-ng for now. Two additions since planning: the LLM router and the sound
contract, both below. First live turns: a question answered in 8.3 s of LLM
time (cold model), a routed "please sit down" in 1.3 s. Builds on `VOICE_RELAY_BRIEF.md`
(the microphone and speaker are installed and validated) and on the 2026-09-05
ears work: DC-free gate, phrase recorder, custom vocabulary, wake moods.

## The ask

Say "Hey Laika". Laika sits, her LED pulses green to show she is listening,
and whatever is said next is transcribed and sent to the local LLM as

```
You are a helpful assistant, the user wants help with the message appended
at the end of this prompt. Instructions: Be concise and brief --- User
message: %s
```

The reply is spoken through the Grove Speaker Plus.

## What exists today, and where it falls short

| Piece | Today | Gap for the ask |
|---|---|---|
| Wake detection | `ears.py` transcribes every utterance; a transcript that starts with the wake phrase fires `voice.phrase` with the rest as `command` and a keyword `intent` | One utterance only: "Hey Laika, sit". A bare "Hey Laika" fires `intent: unknown`, which runs the `acknowledgment` behavior and then nothing listens for a follow-up |
| Reaction | Bindings: sit / rest / stop → motion, greet → greeting, unknown → acknowledgment. Mood: `wake` steady green 2.5 s, `wake_greet` pulsing green | No "listening" state; the LED colour is a timed flash, not a held state |
| LLM | `voice.query_ollama(prompt, system=...)` with the Laika persona, used by the console's typed demo (`/voice/demo`) | Never fed from the microphone; no conversation memory; replies are not length-capped for speech |
| Speech out | `mouth.say(text)`: espeak-ng inside Docker (Eleven Labs if a key is set) → 8 kHz PCM → firmware PWM in 1 KB frames | Works. Robotic voice; playback is real time, so a 10 s answer takes 10 s |
| Self-hearing | none | The speaker sits centimetres from the microphone. Her own reply will be transcribed, and the earlier "Hello Hello Hello" loop came from exactly this |
| Console | Audio input tab shows transcripts and wake badges; Audio output tab has the typed demo | No view of a conversation turn as one thing: heard → asked → answered → spoken, with timings |

## Design

### A state machine in the adapter

A new `dog/app/conversation.py` (`ConversationService`) owns the turn. It is
the only place that knows the sequence; ears, mood, mouth, the arbiter and
the LLM stay independent.

```
IDLE ──wake──▶ LISTENING ──utterance──▶ THINKING ──reply──▶ SPEAKING ──done──▶ IDLE
   │              │ timeout                │ error              │ stop
   │              ▼                        ▼                    ▼
   └──────────── IDLE (soft beep)  spoken apology → IDLE     flush → IDLE
```

| State | Motion | LED | Ears | Sound |
|---|---|---|---|---|
| wake received | submit `idle_sit` to the arbiter at manual priority | `wake` (steady green) for the sit | normal | short buzzer chirp |
| LISTENING | sitting | `listening` (pulsing green), held | listen mode: next utterance goes to the conversation, not to intent matching; max 12 s, 1.0 s silence ends it, window closes after 8 s of nothing | none |
| THINKING | sitting | `thinking` (purple pulse, exists) | muted | none |
| SPEAKING | sitting | `speaking` (teal pulse, exists) | muted, plus 0.5 s tail after the clip completes | the reply |
| back to IDLE | stays sitting; the idle ladder takes over | base mood | normal | none |

Ears changes: a `listen(callback)` mode that hands the next utterance's text
to the service instead of the wake matcher, and a `mute(until)` that drops
packets while the mouth plays. Both are small additions to `EarsService`.

Mood changes: a `hold(mood)` / `release()` pair so LISTENING stays pulsing
green until the state changes, instead of the timed flash. `listening`
becomes a named mood (pulsing green, period 700 ms); `wake_greet` is
retired in its favour, and the badge enum follows.

### The router: tools are the bindings

The transcript does not go to the LLM as a plain question. It goes with a
menu of tools generated live from the bindings on the event `voice.intent`
(the filter's `intent` is the tool's name, the behavior's description its
help text), plus `answer`. Ollama is asked for JSON with a `tool` and a `say`,
and the service fires `voice.intent` with the chosen name so the binding runs
the behavior, then speaks `say`. `answer` means no tool fit and `say` is the
reply. Adding a voice command is therefore one binding row in the console,
and a planning agent later replaces the router with the same contract.
Seeded tools: sit, lie_down, stop, greet, acknowledge. The listening posture
is itself a binding, `conversation.listen` to `idle_sit`.

Information tools are the second kind: they answer from live adapter state
instead of running a behavior. `battery` says "My battery level is 54
percent. About 2 hours left." and is wired in `app.py` from the telemetry
cache and the power tracker's prediction. Each information tool may carry a
keyword pattern; a request that matches ("what's your battery level") skips
the LLM and is answered at once, so the whole turn is the two barks plus
speech. The LLM can still pick it for phrasings the pattern misses ("how much
juice have you got"). Adding one is an `InfoTool(name, description,
answer, keywords)` in `app.py`; candidates: range ahead, WiFi signal, uptime,
the time.

### Sound contract

One bark when the request is picked up (recording starts, or a same-utterance
request is accepted). Two barks before the terminal step: before the chosen
behavior runs, or before the answer is spoken. Barks are the speaker's
`positive_bark` clip with the ears muted for the clip; without a speaker the
buzzer's wake beep stands in. A listening window nobody spoke into ends with
the buzzer's timeout chirp and no speech.

### Same-utterance questions

"Hey Laika, what time is it?" should not force a second turn. Rule: if the
text after the wake phrase matches a motion intent (sit, rest, stop, greet),
run the binding as today; if it is anything else and at least two words, treat
it as the question and skip LISTENING; if it is empty, enter LISTENING.

### The prompt

The template is the user message with `%s` replaced by the transcript; the
router's own instructions are the system prompt. The ask's original wording
("the message appended at the end of this prompt") made the 1b model parrot
the instruction back ("I'm happy to help you with that, message appended"),
so the default became `The user said: "%s"` followed by "Respond to exactly
what the user said", and the router prompt carries two worked examples and
the rule that behavior tools are for requests to act, never for questions.
Routing runs at temperature 0.2. Both the LLM and the two whisper models are
warmed up at adapter start; a cold base.en cost the first request 17.7 s and a
cold Ollama the first answer 8 to 13 s. Two additions the ask does not state
but speech needs:

- a length instruction: "one or two spoken sentences, no lists, no markdown",
  because every sentence costs seconds of playback;
- a hard cap on the reply before TTS (about 320 characters, cut at a sentence
  boundary), because the model will not always obey.

The template lives in a setting (`ears.vocabulary` already has a settings
row; this gets `conversation.prompt`) so it can be edited from the console
without a rebuild.

### Memory

`conversation_messages` already exists in the database and is unused by the
microphone path. Each turn stores the user and assistant messages; the last
six messages ride along in the prompt as context. A turn that starts more
than five minutes after the previous one starts a fresh context.

### Failure handling, all spoken

- Nothing said in the window: soft chirp, LED back to base, no speech.
- Whisper returned no words: "I didn't catch that."
- Ollama unreachable or timed out: "I can't think right now." LED `warn` for
  three seconds.
- Speaker not configured: the reply goes to the transcript log and the
  console only; LED still cycles so the turn is visible.
- "Stop" during playback: the ears are muted, so this is a console button
  (`/mouth/stop`, exists) and a `conversation.cancel` route. A hardware
  option later is the back-touch pad.

### Console

- Audio input tab: a "Conversation" card showing the state machine live
  (idle / listening / thinking / speaking with the matching badge), the last
  turn (heard, asked, replied, and the three latencies: whisper, LLM, first
  sound), and a Cancel button.
- Audio output tab: the typed demo posts into the same service as text in
  place of the microphone, so typing and speaking exercise one code path.
- Both read `GET /conversation` (state, current turn, last ten turns) and the
  relay routes on the orchestrator.

### Adapter API

| Route | Purpose |
|---|---|
| `GET /conversation` | state, current turn, recent turns, the prompt template |
| `POST /conversation/say` `{"text"}` | a turn from typed text (replaces `/voice/demo`'s LLM call) |
| `POST /conversation/cancel` | stop speaking, back to idle |
| `GET/POST /conversation/prompt` | read and edit the template and the reply cap |

## Latency budget, measured pieces

| Step | Today | Note |
|---|---|---|
| Wake heard → sit starts | ~0.7 s whisper + arbiter dispatch | acceptable |
| Question ends → transcript | 0.7 to 2 s with whisper `base` on CPU | `small` would be more accurate on question content, at 2 to 3 s and another 500 MB of RAM |
| LLM reply | 2 to 6 s with `llama3.2:1b` for two sentences | the 1b model is weak on facts; `llama3.2:3b` or `qwen2.5:3b` roughly doubles the time on this CPU. Worth measuring once, then choosing |
| TTS | espeak-ng: well under a second | Piper (local neural voice) is a middle ground between espeak-ng and Eleven Labs; one more model file, no API key |
| Playback | real time at 8 kHz | the reply cap bounds it |

Expect five to eight seconds of silence between the end of the question and
the first spoken word. The THINKING LED and the wake chirp exist to make that
wait legible.

## Embellishments worth deciding now

1. **Follow-up turns.** After she answers, keep listening for another eight
   seconds without a new "Hey Laika". Cheap once the state machine exists;
   make it a setting, default off.
2. **Head turn toward the voice.** There is one microphone, so no direction
   of arrival. Skip.
3. **Interrupt by speech.** Requires the ears to run during playback with echo
   cancellation. Not with this hardware; the console Cancel is the way.
4. **A distinct listening sound.** A two-note rising chirp on wake and a falling
   one on timeout, through the buzzer, both already possible with the `b` token.
5. **Persona.** The ask's template is a neutral assistant. The existing Laika
   persona prompt makes her answer as a dog. Keep both as selectable templates;
   default to the ask's neutral one.

## Build plan

| Step | Work | Effort |
|---|---|---|
| 1 | Ears: listen mode, mute, the same-utterance rule; mood: hold/release and the `listening` mood; tests with the fake transcriber and clock | half a day |
| 2 | `ConversationService`: the state machine, prompt template setting, memory, spoken failures, reply cap; routes; tests with fake LLM and fake mouth | a day |
| 3 | Orchestrator relay routes; console cards on both audio tabs; the typed demo rerouted | half a day |
| 4 | On the dog: measure the latency table, pick the model and whisper size, tune the window and silence timings, listen to espeak-ng versus Piper | an evening with the dog on |
| 5 | Docs: this brief's status, `SENSOR_DATA.md` ears section, READMEs, the runbook's voice step | an hour |

## Open questions for the owner

- Should "Hey Laika, sit" still sit, or should everything after the wake phrase
  go to the LLM? The plan keeps the four motion intents as shortcuts.
- Neutral assistant voice or Laika's persona by default?
- Is a five to eight second wait acceptable, or is it worth buying time with a
  bigger CPU budget (a 3b model) versus a faster answer (the 1b model)?
- Piper for a nicer voice, or keep espeak-ng until the rest works?
