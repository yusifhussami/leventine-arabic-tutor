# Search from Today

The toolbar search was Words-only. Yusif looks up a saved word from Today by its English meaning (`angry`, `Stories`, `coffee`). The first paint waited on `GET /api/items?q=`, which embeds that English gloss before meaning-neighbors can appear.

## Decision

- The same `#search` box shows on **Today** and **Words**. Practice, Topics, Cards, Checklist, and Settings keep it hidden.
- Each keystroke paints **local** matches from the notebook already in memory: English gloss substring/prefix first in spirit, plus spelling, using the same ranks as `search_items` and no network. The `/api/items?q=` call stays debounced at about 280ms.
- When that response arrives, its order and scores replace the local list. Spelling hits that were only in the local list are kept on the end. Near-meanings (cosine on English `lesson_embeddings`) show up in that server pass. Digit Arabizi queries still skip the gloss/semantic path inside `search_items`; that rule is unchanged. The Today box is aimed at English meanings, not Arabizi-first typing.
- A non-empty query on Today replaces the lesson form with a compact spelling + gloss list. Choosing a row opens practice the same way Words does. Clearing the query restores Today. An empty query on Words still loads the full library, grouped by lesson day.
- Queries shorter than two characters come back from `/api/items` as the whole notebook with no `match` tags. Those responses refresh the in-memory cache and are not painted as the result list, so one letter does not wipe Today.
- No new serverless function. Embeddings stay English gloss vectors (`openai/text-embedding-3-small`, 256-d). Arabizi is still not embedded.

## Why

Vercel Hobby is already at 12 functions under `api/`. Semantic search already lives in `search_items`. The delay is the OpenRouter embed on the English gloss, not a missing index. A local cache makes the English lookup immediate; the existing hybrid search fills in neighbors after.

## What I rejected

- A new `/api/search` route.
- Embedding Arabizi, or moving vectors to a separate database.
- Sending Today searches over to the Words tab.
- A separate Arabizi-first search mode on Today.
