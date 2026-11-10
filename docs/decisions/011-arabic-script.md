# Arabic script beside the Arabizi

Yusif wants the Arabic spelling of each Levantine word in its own column, next to the Arabizi.

## Decision

`lesson_items` gains two columns:

| Column | Values |
| --- | --- |
| `arabic_script` | Arabic letters, or empty |
| `arabic_source` | `dictionary`, `ai`, `user`, or empty |

Japanese rows stay empty. The Words list, Today search, the recent list, and the practice title show the Arabic in its own line, right to left, in Noto Naskh Arabic. Edit on the Words row can change it. A change is stored as `user`. Backfill and the automatic fill never overwrite `user`, and they never overwrite a cell that already has letters.

The CSV for Levantine is `Arabizi, Arabic, English, Kind, Date Added, Language`. Japanese exports are unchanged. Importing a sheet that already has an Arabic column stores that spelling as `user`, so a round trip does not send it back to the model.

New words are saved first, without waiting on the lookup. The page then posts `{ "action": "fill-arabic", "ids": [...] }` to `POST /api/items` (the same file as the word list; Hobby still has 12 functions). Local `lexicon.serve` accepts that post. Each call fills at most 16 of those ids.

Existing notebooks are filled with:

```bash
python3 -m lexicon.arabic_script
```

That uses `DATABASE_URL` when it is set, otherwise `lexicon.db`. It walks every open Levantine row once, commits as it goes, and is safe to run again. `--user` limits it to one account. `--limit` stops after that many filled words. Words still open at the end are printed; run it again after setting `OPENROUTER_API_KEY` if the first pass had no model key.

This environment had no `DATABASE_URL` and no OpenRouter key, so production was not filled. A local pass over `data/vocabulary.csv` (619 imported words) matched 273 in Wiktionary, about 44%. The other 346 were left empty for the model. The spellings called out as tricky (`3are9'`, `b-y-a7ko`, `2e9a9`, `qisas`) are in that second group: the dictionary does not have a line whose sound matches, so they wait for the model or for an edit. A leading qaf or a hamza at the edge of a word can be ignored when comparing sounds (`ahwe` still meets قهوة). A hamza in the middle is not ignored, so `hal` does not become هؤلاء.

## Where the spelling comes from

1. **English Wiktionary**, through the Action API (`action=query`, JSON, `maxlag=5`). One request at a time, a named User-Agent, batches of 20 titles, and a `script_cache` row so a repeat does not fetch the page again. The gloss chooses the English entry (`but`, `how are you`). North and South Levantine lines (`apc`, `ajp`) win when the Arabizi matches their spelling or their `tr=` line. Modern Standard or Egyptian is kept only when the consonants match closely, so `bas` becomes بسّ and not لكن. If the translation list misses, the Arabizi is turned into one Arabic guess and kept only when that Wiktionary page’s definition uses the gloss. Those rows are `dictionary`.
2. **Otherwise the existing OpenRouter model** (`google/gemini-3.5-flash-lite`), one JSON call per batch, marked `ai`. No key, or a failed call, leaves the cell empty for a later run.

Living Arabic (livingarabic.com) is the Levantine dictionary I would have used. Its terms forbid automated access and copying, so it is not called. levantinedictionary.com is the site closest to the name “Levantine world”; it has no public API, so it is not scraped either. Wiktionary’s `robots.txt` disallows `/w/` for spiders. The Action API etiquette is the rule for this client: identify yourself, stay serial, cache, and back off on `maxlag` or HTTP 429. Short headwords are stored under CC BY-SA 4.0. The Arabic column header says the dictionary matches come from English Wiktionary.

## What I rejected

- A 13th file under `api/`.
- Scraping Living Arabic or Levantine Dictionary.
- Filling Arabic inside the save request. A lesson paste should return before the lookup.
- Overwriting a spelling the learner edited.
- An Arabic column on Japanese exports.
- Storing the transliteration guess when Wiktionary does not confirm it.
