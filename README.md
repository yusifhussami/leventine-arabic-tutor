# Sawt

Sawt is a learning notebook for lessons, vocabulary, grammar, and sentence homework. After class, capture the words and rules you learned. Write your own sentences, save attempts, and keep your teacher’s corrections alongside the originals. Recap asks you to recall the rule before revealing your notes. The app UI stays English. In Settings you choose the language you’re learning — Levantine Arabic (Arabizi, Arabic speech) or Japanese (romaji, Japanese speech).

Locally it runs on this computer with SQLite. On Vercel each person signs in, and their words live in Postgres. Sentence checks, Talk replies, and speech go to OpenRouter.

## Use it locally

```bash
python3 -m lexicon.serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). No Clerk sign-in is required for that local server.

- **Today** shows unfinished sentence homework and rules due for recap. Quick word capture and CSV import remain in the expandable section below.
- **Lessons** captures a date, teacher, practice goal, words, grammar rules, notes, and homework. Grammar-only lessons and already-known words are supported. Saving creates a sentence brief with explicit word and rule requirements. Drafts use revision checks. Submitted attempts and corrections are separate records. Mark homework ready explicitly.
- **Knowledge** stores explanations, examples, sources, and rule recall. The green-book guide contains original prompts with printed-page references to Matthew Aldrich’s *Levantine Arabic Verbs*. The private scanned PDF is not bundled. Recall ratings schedule another look after one, three, or seven days. Existing vocabulary cards retain FSRS.
- **Words** retains saved vocabulary, Arabic spellings, editing, and CSV export. Its Dictionary tab searches the cached Arwords index in English, Arabic, and available Arabizi. Opening a result loads additional public forms when available. Saving a result is explicit. **Forms** keeps nouns, adjectives, past, bare imperfect, habitual present, imperative, continuous constructions, and participles with their subject, meaning, example, and source. Missing forms remain editable. AI suggestions require review and stay labelled.
- **Cards** keeps existing vocabulary and Anki progress. Arabic writing preferences still use the current saved spellings.
- **Settings** controls account, appearance, and learning language. Arabic and Japanese notebooks remain separate. The iPhone app’s Learn tab uses the same lesson, homework, recall, dictionary, and word-family APIs.

No documented public Arwords API was found. Dictionary lookup uses the existing cached public index, with source links. Arabizi and inflection coverage are incomplete. Additional dictionary forms are fetched only when requested. The app does not infer an entire family from an Arabic root.

Arabizi digits (Arabic): 2 ء/أ, 3 ع, 3' غ, 5 خ, 6 ط, 7 ح, 8 ق, 9 ص, 9' ض. Long ee and oo stay as ee and oo. كيفك is keefak. Japanese mode uses Hepburn romaji on the page and Japanese script for speech.

Arabic spellings are filled after a save, and for words already in the notebook:

```bash
python3 -m lexicon.arabic_script
```

With `DATABASE_URL` set, that writes the hosted notebook. Without it, the local `lexicon.db`. It checks English Wiktionary first (the gloss picks the sense, the Arabizi picks the line) and asks the OpenRouter model when Wiktionary has no match. Running it again skips spellings that are already filled, including ones you edited. `--user` limits it to one account. See [docs/decisions/011-arabic-script.md](docs/decisions/011-arabic-script.md).

The next Preply or Arabic lesson shows in the side column after you paste the private Google Calendar iCal link. That link stays in the database. It is not printed on the page and it is not included in errors.

## Deploy on Vercel

The app stays in Python: static HTML in `public/`, API routes in `api/`, shared logic in `lexicon/`. There are 12 function files under `api/` (Vercel Hobby’s cap). `/api/next-lesson` is rewritten to `api/calendar.py`; lesson topics live in `api/topics.py`.

1. Create a Vercel project from this repo.
2. Create a free [Supabase](https://supabase.com) project. In Project Settings → Database, copy the URI. Prefer the **Transaction** pooler (port `6543`) for Vercel. Set that as `DATABASE_URL`.
3. Create a Clerk application. Set `CLERK_PUBLISHABLE_KEY` and `CLERK_JWKS_URL` (the JWKS URL from the Clerk dashboard).
4. Set `OPENROUTER_API_KEY` (or `GEMINI_API_KEY`).
5. Deploy. Sign-in is required on the hosted URL. Each account only sees its own lessons and calendar link.

Optional local packages for Postgres and JWT checks:

```bash
python3 -m pip install -r requirements.txt
```

To point local serve at the same Supabase database, put `DATABASE_URL` in `.env`. Without it, local serve keeps using `lexicon.db`.

## iPhone app

The installable app is in [`mobile/`](mobile/README.md). It talks to this same API. TestFlight is the install path; Expo Go is the quick way to try a build. See that readme for the steps.

## On a phone (local network)

`127.0.0.1` only works on the computer running the notebook. On the same Wi‑Fi:

```bash
python3 -m lexicon.serve --host 0.0.0.0
```

Then open `http://` followed by this computer's local IP and `:8765`. Anyone on that address can use your words and your API key, so keep it off public networks. The hosted Vercel URL is the better way to share accounts. Speech uses Gemini Flash Lite TTS, about a cent a minute.

## Keep secrets out of git

Copy `.env.example` to `.env` for local values. On Vercel, set the same names in project env.

| Call | Model |
| --- | --- |
| Sentence check and Talk | `google/gemini-3.5-flash-lite` |
| Speech (TTS) | `google/gemini-3.8-flash-lite-tts` |

| Name | What it holds |
| --- | --- |
| `OPENROUTER_API_KEY` | OpenRouter key (header only) |
| `DATABASE_URL` | Supabase Postgres URI (hosted; optional locally) |
| `CLERK_PUBLISHABLE_KEY` | Browser sign-in |
| `CLERK_JWKS_URL` | Server JWT check |
| `lexicon.db` | Local SQLite when `DATABASE_URL` is unset |

`data/vocabulary.csv` is the older sheet export. It has Arabizi and English only, no account details.

Python 3.9 is enough for the local server with no extra packages. Hosted deploy uses `requirements.txt`.

## Decisions

Why each model, the voice loop, and the Vercel shape: [docs/decisions](docs/decisions).

## Tests

```bash
python3 -m unittest discover -s tests
```

## Older terminal commands

The notebook replaced the day-to-day way of practicing, but the earlier commands still load the sheet and run a drill in the terminal:

```bash
python3 -m lexicon.load data/vocabulary.csv lexicon.db
python3 -m lexicon.drill data/vocabulary.csv lexicon.db
```
