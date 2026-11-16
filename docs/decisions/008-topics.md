# Lesson topics from saved words

## Decision

Topics is a tab for the next lesson with Amer (or the current learning language). It proposes one primary situation and a few alternates built from words already in `lesson_items`. It is not another Talk scene.

Done, skipped, and suggested topics are stored per user and learning language. The next generation sees that history and is told not to repeat it.

## Why

Talk already has hard-coded coffee, restaurant, shop, and taxi scenes (`_SCENES` in `lexicon/notebook.py`). Those are useful drills and the wrong place to invent “what should we talk about on Tuesday.” Yusif already has those situations. He needs a topic that uses glosses he saved: work, family, an exam, Manchester, being tired.

The model only helps if it sees his real spellings. A generic prompt would fall back to the same tourist scripts.

## How

1. `select_topic_words` sends the newest spellings plus a spread of older ones, and the prompt cuts that list so it stays small.
2. Tourist scenes are forbidden unless the **newest** words name them. An old `ahwe = coffee` in the diverse tail can still be cited, but it does not unlock “ordering coffee.”
3. The model call is the same OpenRouter chat as Talk: `complete` / `_json_body`, Gemini flash lite, strict JSON. The key stays on the server.
4. Each accepted topic is a `lesson_topics` row: title, `created_at`, status (`suggested`, `done`, `skipped`), target word ids and spellings, and the JSON payload. Rows are scoped by `user_id` and `language`.
5. The page can mark a card done, skip it, or undo. Generating again sends recent titles in the prompt. A rejected generic reply is repaired once.

## Vercel function cap

Hobby allows 12 Python files under `api/`. Topics needs its own handler (`api/topics.py`). `api/next-lesson.py` was only a GET in front of `calendar_feed.next_lesson`, so that read moved into `api/calendar.py`. `vercel.json` rewrites `/api/next-lesson` to `/api/calendar?next=1`. Local `lexicon.serve` still serves `/api/next-lesson` directly. The file count stays 12.

## What I rejected

- A 13th file under `api/`.
- Folding Topics into Talk scenes. That would put every suggestion back in a café.
- Generating in the browser. The word list and the API key would both leak.
- Letting any saved coffee word, however old, permit a coffee-shop topic.
