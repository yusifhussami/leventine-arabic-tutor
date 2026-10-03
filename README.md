# Sawt

Sawt is a practice notebook. After class you paste new words with meanings. Before the next class you talk with those words, or write a sentence with one of them. The app UI stays English. In Settings you choose the language you’re learning — Levantine Arabic (Arabizi, Arabic speech) or Japanese (romaji, Japanese speech).

Locally it runs on this computer with SQLite. On Vercel each person signs in, and their words live in Postgres. Sentence checks, Talk replies, and speech go to OpenRouter.

## Use it locally

```bash
python3 -m lexicon.serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). No Clerk sign-in is required for that local server.

- **Today** is where a lesson gets pasted. Arabic: `baza5 = fancy` or `practice - tadreeb`. Japanese: `hello - konnichiwa` or `mizu = water` (romaji). Preview shows the split before you save.
- **Settings** (under Words) has account sign-in and **Language you’re learning** (Levantine Arabic or Japanese). UI stays English; mic, TTS, spellings, and your word list follow the choice — each language has its own notebook on the account. **Import a CSV** on Today: Arabic sheets use Word/Arabizi + Meaning; Japanese sheets use Kanji + Kana (hiragana/katakana) + Meaning — practice stores kana, with kanji kept on the meaning line. Date Added groups rows by lesson day; rows without a date use the lesson date field.
- **Words** lists everything saved, grouped by the lesson date. Edit changes the Latin spelling or the meaning. A spelling with a space is stored as a phrase.
- **Practice** is the voice page. Tap the circle to talk. Coffee, Restaurant, Shop, and Taxi put Sawt in that place. You can also type a line, or open a saved word and check one sentence. Light and dark follow the system appearance.

Arabizi digits (Arabic): 2 ء/أ, 3 ع, 3' غ, 5 خ, 6 ط, 7 ح, 8 ق, 9 ص, 9' ض. Long ee and oo stay as ee and oo. كيفك is keefak. Japanese mode uses Hepburn romaji on the page and Japanese script for speech.

The next Preply or Arabic lesson shows in the side column after you paste the private Google Calendar iCal link. That link stays in the database. It is not printed on the page and it is not included in errors.

## Deploy on Vercel

The app stays in Python: static HTML in `public/`, API routes in `api/`, shared logic in `lexicon/`.

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
