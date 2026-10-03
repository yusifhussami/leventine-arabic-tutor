# Secrets stay local

## API key

**Why:** The same key pays for judgments, Talk, embeddings, and TTS. It must never ship in HTML or in a query string.

**How:** `read_api_key()` loads `OPENROUTER_API_KEY` or `GEMINI_API_KEY` from the environment or a gitignored `.env`. Every OpenRouter request puts it in an `Authorization` header. `.env` and `lexicon.db` are ignored. `.env.example` is blank. Serving with `--host 0.0.0.0` shares that key with anyone on the LAN who opens the page, so that bind is only for private Wi‑Fi.

## Calendar link

**Why:** A Google Calendar private iCal URL is a secret. Printing it in an error or on the page would leak the feed.

**How:** The URL is stored in the local settings table. The page only gets whether a calendar is connected and the next lesson title/time. Fetch failures become a generic “could not read the calendar”. Only `calendar.google.com` hosts are accepted when saving a link.
