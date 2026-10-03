# Voice loop

I wanted a real conversation that stays cheap. A realtime voice API would keep a socket open and bill the whole stream. Sawt does not do that.

## Decision

- **Speech in:** the browser’s SpeechRecognition — `ar-SA` for English accounts, `ja-JP` for Japanese accounts (they speak Japanese; Sawt still answers in Levantine).
- **Brain:** one Flash Lite chat turn per pause (`talk()`).
- **Speech out:** one Flash Lite TTS call per reply (`arabic_speech()`).

## How it runs

1. Practice shows the orb. Tap starts listening (or a Situation starts with Sawt’s first line).
2. Recognition is continuous with interim results. A reply only fires after about 1.8 seconds of silence, so the bot does not cut me off mid-sentence.
3. The page POSTs the last few turns to `/api/talk`. The server builds the prompt, calls Flash Lite, and returns Arabizi, English, Arabic script, and optional correction / better line.
4. The page shows my line as Arabizi + English (not Arabic script). Sawt’s line is Arabizi + English. If there is a correction, it shows under that turn.
5. The page POSTs the Arabic script to `/api/speak`, plays the WAV, waits about 700 ms so the mic does not hear Sawt, then listens again.

Typing on the same page uses the same `/api/talk` and `/api/speak` path. It just skips the mic.

## What I rejected

- Mac `say -v Majed`: only the laptop speaker hears it.
- Browser TTS for Arabic: unreliable with the voices I had.
- Streaming / realtime voice: too expensive for a lesson notebook I open for a few minutes.
