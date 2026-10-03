# English / Arabizi vs Japanese / romaji

Sawt teaches Levantine Arabic. An English account writes Latin Levantine as Arabizi (digit letters). A Japanese account writes it as romaji (ローマ字). Spoken Arabic does not switch.

## Decision

- **Account language** is English (`en`) or Japanese (`ja`), stored in `settings` as `language`.
- **English:** UI + glosses in English; Talk / notebook Latin spelling is Arabizi (`7elo`, `8addeesh`, digit map).
- **Japanese:** UI + glosses in Japanese; Talk / notebook Latin spelling is romaji (`helo`, `qaddeesh`, no digit letters).
- **Speech in follows the account:** English mic is `ar-SA`; Japanese mic is `ja-JP` so they can talk in Japanese. **Speech out stays Arabic script** (`arabic_for_speech` strips romaji / kana). When they speak Japanese, Talk keeps that line in history, shows it under You, puts Levantine romaji under it, and Sawt answers in Levantine. Schema field names still say `arabizi` / `english`. The voice orb tracks `voicePhase` so Japanese labels do not break listening / speaking.

## How

1. Settings posts `/api/settings` with `{ "language": "ja" }` or `"en"`.
2. `talk()` picks `_SCENES["romaji"]` or `_SCENES["arabizi"]` and a matching spelling block. `better` and `arabizi` use that Latin system; `arabic` stays script for speech.
3. Judgment comments use the metalanguage; the tutor line names Arabizi or romaji to match the account.
4. Saved spellings are whatever the learner pasted. A Japanese notebook should paste romaji + Japanese meanings (`練習 - tadreeb`, `qaddeesh = いくら`).

## What I rejected

- Changing SpeechRecognition or TTS language with the setting.
- Renaming Talk schema keys (would break the page and tests for no gain).
- Auto-converting every stored Arabizi row to romaji on switch (notebook stays the source of truth).
