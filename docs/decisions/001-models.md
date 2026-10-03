# Models

Everything paid goes through one OpenRouter key. The browser never sees the key. Headers only; nothing in the URL.

## Chat: `google/gemini-3.5-flash-lite`

**Used for:** sentence check (`lexicon/judge.py`) and Talk / Situations (`lexicon/notebook.py` → `talk()`).

**Why:** I need a short JSON reply, not a long essay. Flash Lite is the cheap Gemini chat model on OpenRouter. Temperature is 0 for judgments (same input should get the same check) and 0.4 for Talk (a conversation needs a little variation). Reasoning effort is set to `minimal` so the model does not burn tokens thinking out loud.

**How:**

1. Build a prompt that includes the saved words (or the practice card) and the learner line.
2. POST `https://openrouter.ai/api/v1/chat/completions` with a strict JSON schema (`response_format`).
3. Parse the schema fields in Python. Judgment fields: `uses_target`, `fits_meaning`, `comment`. Talk fields: `you_arabizi`, `you_english`, `arabic`, `arabizi`, `english`, `correction`, `better`.
4. Space sentence-check calls by about 4 seconds so a typed burst stays under the minute cap. Talk uses its own ~0.25 s gap so voice turns are not stuck waiting. Retry 408 / 429 / 5xx a few times.

Talk also caps `max_tokens` at 280 so a turn stays short and cheap.

## Speech: `google/gemini-3.8-flash-lite-tts`

**Used for:** reading the Arabic line out loud (`lexicon/speak.py` → `/api/speak`).

**Why:** Browser `speechSynthesis` and Mac `say` only help on this machine. A phone needs audio in the HTTP response. Flash Lite TTS is the cheap speech model on the same key, about a cent a minute. Voice is `Kore`.

**How:**

1. POST `https://openrouter.ai/api/v1/audio/speech` with the Arabic script, voice `Kore`, `response_format: pcm`.
2. Gemini TTS only accepts PCM here; `mp3` returns 400.
3. Wrap 16-bit mono PCM at 24 kHz as WAV and return `audio/wav`.
4. The page plays one reused `Audio` element (unlocked on the first tap so iOS allows later playback).

Levantine will sound closer to MSA than Beirut dialect. That is the trade for cost and phone playback.

## Embeddings: `openai/text-embedding-3-small`

**Used for:** “similar meanings” next to a practice word (`lexicon/notebook.py`).

**Why:** I compare English glosses, not Arabizi spellings. A small embedding with 256 dimensions is enough to rank nearby meanings without shipping a large vector store.

**How:** Embed the gloss when a lesson is saved or a meaning changes. Store the vector next to the item. At practice time, cosine-rank other items and show a short list. Arabizi is never what gets embedded.
