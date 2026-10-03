# Vocab window and spelling

## 180 newest spellings

**Why:** Sending every saved row on every Talk turn would grow the prompt with the notebook. Cost and latency go up, and older words crowd out the ones from recent lessons.

**How:** Before each Talk call, drop exact duplicate spelling+meaning pairs, then take unique spellings newest-first up to `_TALK_WORDS = 180`. That list is what the model sees. Same spelling with a different gloss still stays in the library; only exact copies are dropped.

## Arabizi is mine, not the model’s

**Why:** Models invent spellings (`kayfak`, `kifak`). I write كيفك as `keefak`, and I use digit letters (2, 3, 5, 6, 7, 8, 9). If Talk drifts, practice stops matching the notebook.

**How:** The Talk prompt tells the model to copy a saved word exactly when it uses one, lists the digit map, and states that كيفك is `keefak`. The page never shows my utterance as Arabic script; it shows `you_arabizi` and `you_english` from the model. Tests assert `keefak` is in the prompt.

## Structured output

**Why:** Free-form chat is hard to put under You / Sawt on the page, and hard to send only the Arabic line to TTS.

**How:** Strict JSON schema on the chat call. Talk always returns the seven string fields. Judgment always returns the three judgment fields. Python reads those keys; the UI and TTS never scrape prose.
