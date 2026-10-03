# Language you’re learning

Settings chooses the language being practiced. The app UI stays English either way. Mic, TTS, talk prompts, scenes, and Latin spelling follow that choice.

## Decision

- **Learning language** is `arabic` (Levantine) or `japanese`, stored in `settings` as `language`. Legacy values `en` / `ja` still map to those.
- **Levantine Arabic:** Arabizi on the page, English meanings, mic `ar-SA`, TTS Arabic script, Levantine talk/scenes.
- **Japanese:** romaji on the page, English meanings, mic `ja-JP`, TTS Japanese script (kana/kanji), Japanese talk/scenes.
- Talk JSON still uses field names `arabizi` / `arabic` / `english` for compatibility. For Japanese, `arabizi` holds romaji and `arabic` holds Japanese script for speech.
- Each account keeps a separate word notebook per learning language (`lessons.language`). Switching language swaps the library; Arabic words do not appear in Japanese mode and the reverse.
- The sidebar brand flips between صوت and 音 when the learning language changes.

## How

1. Settings posts `/api/settings` with `{ "language": "japanese" }` or `"arabic"`.
2. Saves, imports, list, search, and talk all read/write lessons for that language only.
3. `/api/talk` and `/api/speak` use that language (speak also accepts `language` in the body).
4. `text_for_speech()` rejects Latin-only input so romaji never reaches TTS.

## What I rejected

- Translating the whole app UI.
- One shared “metalanguage” switch that left TTS stuck on Arabic while claiming Japanese mode.
