# Voice loop

I wanted a real conversation that stays cheap. A realtime voice API would keep a socket open and bill the whole stream. Sawt does not do that.

## Decision

- **Speech in:** the browser’s SpeechRecognition — `ar-SA` when learning Arabic, `ja-JP` when learning Japanese.
- **Brain:** one Flash Lite chat turn per pause (`talk()`).
- **Speech out:** one Flash Lite TTS call per reply (`speak_text()`), in the learning language’s script.

## How it runs

1. Practice shows the orb. Tap starts listening (or a Situation starts with Sawt’s first line).
2. Recognition is continuous with interim results. A final chunk can send after about 0.7 s of quiet; interim speech waits about 1.1 s, so the bot does not cut me off mid-sentence.
3. The page POSTs the last few turns to `/api/talk` with `speak: true`. The server builds the prompt, calls Flash Lite, streams the text reply as NDJSON, then runs Flash Lite TTS on the same request.
4. The page paints my line and Sawt’s line as soon as the first NDJSON line arrives (Arabizi + English; correction under the turn when present).
5. The second NDJSON line is the WAV (base64). The page plays it, waits about 300 ms so the mic does not hear Sawt, then listens again. `/api/speak` remains for fallback.

Typing on the same page uses the same `/api/talk` and `/api/speak` path. It just skips the mic.

## What I rejected

- Mac `say -v Majed`: only the laptop speaker hears it.
- Browser TTS for Arabic: unreliable with the voices I had.
- Streaming / realtime voice: too expensive for a lesson notebook I open for a few minutes.
