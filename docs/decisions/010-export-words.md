# Export words as CSV

Yusif wants every saved word in a file that opens in Excel and Google Sheets.

## Decision

The Words tab has an **Export CSV** button. It downloads the signed-in user’s words for the language currently selected in Settings. The file is `sawt-words-YYYY-MM-DD.csv` (the date is UTC).

`GET /api/items?format=csv` writes that file. The word list was already `GET /api/items`. A search query on the same URL is ignored for the export, so the file is the whole notebook, not the rows on screen. Local `lexicon.serve` accepts the same query.

Columns, in order:

| Column | Stored as |
| --- | --- |
| Arabizi, or Spelling when the language is Japanese | `lesson_items.spelling` |
| Arabic (Levantine files only; see 011) | `lesson_items.arabic_script` |
| English | `lesson_items.gloss` |
| Kind | `word` or `phrase` |
| Date Added | `lessons.learned_on` |
| Language | Levantine Arabic or Japanese |

Rows are oldest lesson day first, then spelling. The file is UTF-8 with a BOM, Windows line endings, and normal CSV quoting (commas, quotes, and newlines). Arabizi such as `3are9'` and `b-y-a7ko` is written as stored. The spelling, English, and date headers are names the CSV import already accepts, so the file can be imported again. Levantine files also include an Arabic column beside Arabizi; see 011.

The page fetches the file with the Clerk bearer token and saves the blob. A plain link would not send that token.

## Why

Vercel Hobby allows 12 Python files under `api/`, and this project is already at 12. A new `api/export.py` would not deploy. The items handler already loads this user’s words for the selected language, after the same duplicate cleanup as the Words list.

Generating the CSV in the browser would have copied the quoting rules into the page, with no Python test. The formatter lives next to the notebook so the quoting, the BOM, and the column order are tested once.

Examples, topics, and a per-word status are not fields on a saved word. Topics are their own table. Japanese kanji, when it was imported, already sits on the English line (`hello · 今日は`). Arabic script was added in 011 and is its own column on Levantine exports only.

## What I rejected

- A 13th file under `api/`.
- An `.xlsx` file. That needs another library, and CSV with a BOM already opens in Excel and Sheets.
- A Markdown export.
- One file that mixes Arabic and Japanese. Each language is its own notebook. The Language column says which one this file is.
- Exporting only the search hits.
- Client-side CSV built from the in-memory list, which can be a search result.
