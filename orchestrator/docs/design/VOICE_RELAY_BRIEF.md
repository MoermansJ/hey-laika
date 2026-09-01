# Planning Brief — Voice Relay (talk to Laika, Laika talks to the LLM)

**Date:** 2026-09-01 · **Status:** hardware ordered, ready to build on arrival
**Goal:** speak a free-form sentence to the dog; it is captured on-robot,
transcribed host-side, and handed to the decision layer as a prompt — the dog
becomes an LLM prompting relay.

## Hardware (final, 2026-09-01 — supersedes the MAX9814 plan)

- **Capture: the XIAO ESP32S3 Sense satellite's built-in PDM digital MEMS
  microphone.** Digital samples, no ADC noise floor — better than the
  MAX9814-into-ADC path, already on the vision satellite, zero soldering.
  **MAX9814 dropped from the order.** Consequences:
  - The entire BiBoard audio firmware work (I2S-ADC task, ring buffer,
    event_audio WS frames) is DELETED from the plan — the XIAO streams
    16 kHz audio to the adapter over its OWN WiFi; the dog's firmware and
    WS are untouched.
  - Wake word v1 moves host-side: openWakeWord on the continuous stream
    (LAN-only, processed locally). The Petoi module is no longer in the
    trigger path (its presets failed the owner's voice anyway); it remains
    the dog's canned-phrase speaker. Later refinement if wanted: on-XIAO
    micro wake-word restores "nothing leaves the dog until wake".
  - Privacy framing updated honestly: audio continuously reaches the PC,
    local-only processing.
- *(superseded)* MAX9814 rationale kept for the record: AGC solved the
  fixed-gain problem that disqualified the Grove Analog Microphone
  ("not a recording device" per Seeed).
- **Grove-to-female-jumper conversion cable** → any analog socket
  (ANALOG1..4 = GPIO 34/35 or 32/36/39). Three wires: VDD→VCC, GND→GND,
  OUT→signal.
- Mount: stamp-sized board, velcro/tape near the head.
- **Grove Speaker Plus (the mouth, decided 2026-09-01):** PWM-driven amp +
  separate 2 W enclosed speaker with volume pot. Speech is possible ONLY via
  single-pin sigma-delta/PWM synthesis — a proper I2S DAC amp needs 3 output
  pins and the board has exactly 2 solder-free output pins (GPIO 9/10, UART
  socket), which structurally rules real I2S audio out. Pipeline mirror of
  the mic path: host TTS → downsampled WAV streamed down the WS → firmware
  PWM playback. Expect intelligible walkie-talkie quality.
- **Socket map:** UART socket's two signal pins are split via jumper cables —
  ultrasonic ranger on one of GPIO 9/10, Speaker Plus on the other (validate
  the ultrasonic FIRST on arrival day; its pin determines the speaker's).
  That socket is then fully spent. Mic on an analog socket.
- **Rejected: Grove Recorder v3.0 (ISD9160)** — mic+record+playback in one,
  but audio is sealed in its own flash with a button-style Grove interface:
  no way to extract audio for transcription, no arbitrary playback for TTS.
  Replaces nothing in this pipeline.

## What the audio validation (2026-09-01) established

| Component | Verdict |
|---|---|
| Buzzer (GPIO2, tone/melody via `b` token) | ✅ works — this is the only sound output; NO DAC exists on BiBoard V1 (GPIO25/26 are the voice-module UART) |
| Voice module speaker + mic | ✅ works — speaks confirmations, hears phrases |
| Voice module preset phrases | ❌ unusable for the owner's voice (~10% on the best phrase with servos active, ~0% otherwise; once misheard "Bing-Bing" as "Di-Di" and switched itself to Chinese) |
| Voice module custom phrases | untested — matched against the OWNER'S OWN recording, so odds are far better; this is the wake-word candidate |
| Audio capture on current hardware | ❌ impossible — the module emits 1-byte codes only, never audio |

Design lessons: no wake word exists on the module (presets are matched bare);
language can flip by mishearing, so language is set over serial (`XAa`) and
the spoken switch phrases are avoided; capture happens in a **listening
posture** (servos rested — active balancing wrecked recognition).

## Pipeline

```
MAX9814 → ESP32 I2S-ADC DMA, 16 kHz mono, continuous ~1 s ring buffer
   (audio never leaves the dog un-triggered — privacy by construction)
        │  trigger: voice module custom slot ("Hey Laika", trained in the
        │  owner's voice via XAe/XAf; firmware remaps the slot from its
        │  current skill to "start capture")
        ▼
firmware streams ring buffer + ~6 s live audio as WS event frames
   (event_audio, base64 PCM chunks — same pattern as event_rssi)
        ▼
adapter reassembles → WAV → faster-whisper (local, CPU) → transcript
        ▼
decision layer prompt (Ollama default / Claude opt-in) with context:
   personality state, behavior catalog, (later) room list
        ├─ command → arbiter submit, cause {type: "voice", transcript}
        └─ question → host-side TTS answer from the PC speaker
        ▼
Mind page shows: heard "…" → decided "…"  (ordinary provenance)
```

- **Wake fallback:** if the trained phrase also recognizes poorly, wake-word
  detection moves host-side (openWakeWord on the same stream); the module
  retires to being the dog's speaker. The MAX9814 carries both jobs.
- **Dog has no speech output** (buzzer + the module's canned phrases only):
  answers are spoken by the PC (`voice.py` TTS path) while the dog chirps
  and animates in character.

## Build plan (~2–4 sessions once the mic arrives)

1. **Firmware:** I2S-ADC capture task + ring buffer; `event_audio` WS frames;
   custom-slot remap ("Hey Laika" → capture, not skill); bench-validate the
   ADC signal (speak → sane waveform) before any streaming.
2. **Adapter:** audio reassembly endpoint, faster-whisper integration,
   transcript → decision-layer hook with voice provenance.
3. **End-of-utterance:** start fixed ~6 s window; upgrade to host-side VAD.
4. **Training session (owner):** "start learning" (`XAe`) → speak the wake
   phrase (≤6 syllables, nothing resembling Bing-Bing/Di-Di) → `XAf`.

## Open questions

1. Wake phrase choice ("Hey Laika" = 3 syllables, distinct — good default).
2. Whisper model size (start `small`/`base`; latency vs accuracy on this PC).
3. Capture sample rate 16 kHz vs 8 kHz (start 16 kHz; halve if WS strains).
4. Should transcripts persist (a "things the owner said" log feeding
   personality/memory)? Lean yes — it is provenance like everything else.

**References:** `docs/design/BEHAVIOR_FRAMEWORK_BRIEF.md` (voice.phrase event,
arbiter causes), `docs/design/OBSERVABILITY_MIND_BRIEF.md` (Mind page),
`opencat-esp32/src/voice.h` (module protocol, custom slots, XAe/XAf),
`docs.petoi.com/extensible-modules/voice-command-module` (no wake word,
preset list, training flow), BiBoard V1 pins: `opencat-esp32/src/OpenCat.h`
(BUZZER=2, VOICE UART=25/26, ANALOG1..4).
