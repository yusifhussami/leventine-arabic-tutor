"""Lesson topics grounded in the words Yusif already saved.

Talk scenes (coffee, restaurant, shop, taxi) stay hard-coded on the Practice
page. Topics is the opposite: one situation built from his glosses, plus a
short history so the next suggestion does not repeat a lesson he already did.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from lexicon.db import LOCAL_USER, insert_id
from lexicon.judge import MODEL, RateLimiter, _json_body, complete, message_text
from lexicon.load import normalize_meaning, normalize_word
from lexicon.notebook import drop_exact_duplicates, list_items
from lexicon.prefs import (
    get_language,
    learning_label,
    normalize_language,
    writing_system_label,
)

STATUSES = ("suggested", "done", "skipped")
NEWEST_COUNT = 40
DIVERSE_COUNT = 20
MIN_SAVED_WORDS = 3
MIN_TARGET_WORDS = 2
MAX_TARGET_WORDS = 6
MAX_TOPICS = 4
HISTORY_LIMIT = 24
LIST_LIMIT = 100
VOCAB_CHAR_BUDGET = 4500

_TOPIC_PACE = RateLimiter(min_interval=0.25)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_LEVANTINE = re.compile(
    r"\b(keefak|kifak|ahlan|mar7aba|ahwe|baddi|yalla|habibi|shu|shou)\b",
    re.IGNORECASE,
)
_JAPANESE_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")

# Tourist scenes Talk already covers. A scene is allowed only when the newest
# saved words name it. Output is scanned with `hit`; the word list with `support`.
_SCENES = (
    {
        "id": "coffee",
        "label": "ordering coffee",
        "support": re.compile(
            r"\b(coffees?|caf[eé]s?|ahwe|qahw[ae]|lattes?|espressos?|cappuccinos?)\b",
            re.IGNORECASE,
        ),
        "hit": re.compile(
            r"\b(coffees?|caf[eé]s?|coffee shops?|ordering coffee)\b",
            re.IGNORECASE,
        ),
    },
    {
        "id": "taxi",
        "label": "taking a taxi",
        "support": re.compile(
            r"\b(taxis?|cabs?|taxi driver|cab driver)\b",
            re.IGNORECASE,
        ),
        "hit": re.compile(r"\b(taxis?|cabs?|taxi rides?|taking a taxi)\b", re.IGNORECASE),
    },
    {
        "id": "restaurant",
        "label": "at the restaurant",
        "support": re.compile(
            r"\b(restaurants?|waiters?|waitresses?|appetizers?)\b",
            re.IGNORECASE,
        ),
        "hit": re.compile(
            r"\b(restaurants?|ordering (?:food|a meal)|at the restaurant)\b",
            re.IGNORECASE,
        ),
    },
    {
        "id": "shopping",
        "label": "shopping",
        "support": re.compile(
            r"\b(shopping|shopkeepers?|grocers?|groceries)\b",
            re.IGNORECASE,
        ),
        "hit": re.compile(
            r"\b(shopping|shopkeepers?|at the shops?|at the stores?|at the markets?)\b",
            re.IGNORECASE,
        ),
    },
)

_TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "target_words": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "spelling": {"type": "string"},
                                "gloss": {"type": "string"},
                            },
                            "required": ["spelling", "gloss"],
                            "additionalProperties": False,
                        },
                    },
                    "prompts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "why", "target_words", "prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def _unique_items(items: list[dict]) -> list[dict]:
    """Newest-first items, one row per spelling."""
    seen: set[str] = set()
    chosen = []
    for item in items:
        key = normalize_word(str(item.get("spelling") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        chosen.append(item)
    return chosen


def _spread(items: list[dict], count: int) -> list[dict]:
    """Evenly spaced rows, including the first and last of the older tail."""
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    picked: list[dict] = []
    seen: set[int] = set()
    for step in range(count):
        index = round(step * (len(items) - 1) / (count - 1))
        if index in seen:
            continue
        seen.add(index)
        picked.append(items[index])
    return picked


def select_topic_words(items: list[dict]) -> list[dict]:
    """Newest spellings plus a spread of older ones, capped for the prompt."""
    unique = _unique_items(items)
    newest = unique[:NEWEST_COUNT]
    diverse = _spread(unique[NEWEST_COUNT:], DIVERSE_COUNT)
    return newest + diverse


def newest_support_words(items: list[dict]) -> list[dict]:
    """Words that decide whether a tourist scene is allowed."""
    return _unique_items(items)[:NEWEST_COUNT]


def _word_blob(words: list[dict]) -> str:
    return "\n".join(
        f"{item.get('spelling') or ''} {item.get('gloss') or ''}" for item in words
    )


def forbidden_scene_ids(words: list[dict]) -> list[str]:
    """Tourist scenes the given words do not force."""
    blob = _word_blob(words)
    return [scene["id"] for scene in _SCENES if not scene["support"].search(blob)]


def scene_label(scene_id: str) -> str:
    for scene in _SCENES:
        if scene["id"] == scene_id:
            return scene["label"]
    return scene_id


def _fit_lines(lines: list[str], limit: int) -> list[str]:
    kept: list[str] = []
    size = 0
    for line in lines:
        extra = len(line) + 1
        if kept and size + extra > limit:
            break
        kept.append(line)
        size += extra
    return kept


def _title_key(title: str) -> str:
    return " ".join(title.strip().casefold().split())


def _history_lines(history: list[dict]) -> list[str]:
    lines = []
    for item in history[:HISTORY_LIMIT]:
        title = " ".join(str(item.get("title") or "").split())
        status = str(item.get("status") or "").strip()
        if not title or status not in STATUSES:
            continue
        lines.append(f"- {status}: {title}")
    return lines


def build_topic_prompt(
    words: list[dict],
    history: list[dict],
    language: str,
    support_words: list[dict] | None = None,
) -> str:
    """Prompt for one primary topic and a few alternates.

    `words` is what the model may cite. `support_words` (default: those same
    words) decides which tourist scenes are forbidden. Pass the newest slice
    as support so an old coffee gloss in the diverse tail does not unlock a
    café scene.
    """
    learning = normalize_language(language)
    lines = _fit_lines(
        [
            f"{item.get('spelling')} = {item.get('gloss') or ''}"
            for item in words
            if item.get("spelling")
        ],
        VOCAB_CHAR_BUDGET,
    )
    support = words if support_words is None else support_words
    forbidden = forbidden_scene_ids(support)
    forbid_block = ""
    if forbidden:
        bullets = "\n".join(f"- {scene_label(scene_id)}" for scene_id in forbidden)
        forbid_block = (
            "FORBIDDEN SCENES (the newest saved words do not support these — "
            "do not use them, and do not mention them):\n"
            f"{bullets}\n"
        )
    used = _history_lines(history)
    history_block = ""
    if used:
        history_block = (
            "Already used — do not repeat these titles or the same situation:\n"
            + "\n".join(used)
            + "\n"
        )
    if learning == "japanese":
        who = (
            "The learner is studying Japanese with a teacher.\n"
            "Propose one primary topic and 2 or 3 alternates for the next lesson.\n"
            "Titles and why-sentences are English.\n"
            "Starter prompts are short spoken lines in Hepburn romaji, "
            "not Levantine Arabizi and not textbook keigo drills.\n"
        )
    else:
        who = (
            "The learner is Yusif. The teacher is Amer. "
            "They speak Levantine Arabic in lessons.\n"
            "Propose one primary topic and 2 or 3 alternates they can talk about next lesson.\n"
            "Titles and why-sentences are English.\n"
            "Starter prompts are short questions Amer or Yusif could say, "
            "in Levantine Arabizi (lowercase, digit letters: "
            "2 for ء/أ, 3 for ع, 5 for خ, 6 for ط, 7 for ح, 8 for ق, 9 for ص). "
            "Not MSA textbook Arabic. Not Japanese.\n"
        )
    vocab = "\n".join(lines)
    return (
        f"LANGUAGE LOCK: {learning}\n"
        f"You are picking a conversation topic for a {learning_label(learning)} lesson.\n"
        "The app UI stays English. Example lines use "
        f"{writing_system_label(learning)}.\n"
        f"{who}"
        "Each topic must combine several of the saved glosses into one specific situation "
        "(work, family, feelings, study, daily life — only when these glosses support it).\n"
        "Do not recycle a stock tourist dialogue that these glosses do not force.\n"
        "The first array item is the primary topic. The rest are alternates.\n"
        "For each topic return title, why (1 or 2 sentences that name the glosses), "
        "target_words (3 to 6 objects; copy spelling and gloss exactly from the list), "
        "and prompts (2 or 3 starter lines).\n"
        f"{forbid_block}"
        f"{history_block}"
        "Saved words (spelling = English gloss). Cite these spellings. "
        "Do not invent vocabulary:\n"
        f"{vocab}\n"
    )


def _parse_model_json(payload: dict) -> dict:
    text = message_text(payload).strip()
    text = _FENCE.sub("", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model returned no topics")
    return data


def _topic_model_json(prompt: str, api_key: str, opener, pace) -> dict:
    body = _json_body(prompt, "lesson_topics", _TOPIC_SCHEMA, temperature=0.7)
    body["model"] = MODEL
    body["max_tokens"] = 1000
    payload = complete(body, api_key, opener, pace=pace)
    return _parse_model_json(payload)


def _clean_text(value, width: int) -> str:
    return " ".join(str(value or "").split())[:width]


def _clean_lines(value, limit: int, width: int) -> list[str]:
    if not isinstance(value, list):
        return []
    lines = []
    for item in value:
        text = _clean_text(item, width)
        if not text:
            continue
        lines.append(text)
        if len(lines) == limit:
            break
    return lines


def _titles_clash(title: str, history: list[dict]) -> bool:
    key = _title_key(title)
    if not key:
        return True
    for item in history:
        other = _title_key(str(item.get("title") or ""))
        if not other:
            continue
        if key == other:
            return True
        if len(key) >= 12 and len(other) >= 12 and (key in other or other in key):
            return True
    return False


def _library_index(library: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for item in library:
        key = normalize_word(str(item.get("spelling") or ""))
        if not key or "id" not in item:
            continue
        index.setdefault(key, []).append(item)
    return index


def _resolve_word(entry: dict, index: dict[str, list[dict]]) -> dict | None:
    if not isinstance(entry, dict):
        return None
    matches = index.get(normalize_word(str(entry.get("spelling") or ""))) or []
    if not matches:
        return None
    gloss = normalize_meaning(str(entry.get("gloss") or ""))
    chosen = matches[0]
    if gloss:
        for item in matches:
            if normalize_meaning(str(item.get("gloss") or "")) == gloss:
                chosen = item
                break
    return {
        "id": int(chosen["id"]),
        "spelling": str(chosen["spelling"]),
        "gloss": str(chosen["gloss"]),
    }


def _forbidden_hit(text: str, forbidden_ids: list[str]) -> str | None:
    banned = set(forbidden_ids)
    for scene in _SCENES:
        if scene["id"] in banned and scene["hit"].search(text):
            return scene["id"]
    return None


def _raw_topics(raw: dict) -> list:
    topics = raw.get("topics") if isinstance(raw, dict) else None
    if isinstance(topics, dict):
        return [topics]
    if isinstance(topics, list):
        return topics
    if isinstance(raw, dict) and raw.get("title"):
        return [raw]
    return []


def _screen_topic(
    item: dict,
    index: dict[str, list[dict]],
    forbidden_ids: list[str],
    history: list[dict],
    language: str,
) -> tuple[dict | None, str]:
    if not isinstance(item, dict):
        return None, "a topic was not an object"
    title = _clean_text(item.get("title"), 90)
    why = _clean_text(item.get("why"), 600)
    prompts = _clean_lines(item.get("prompts"), 4, 220)
    if not title:
        return None, "missing a title"
    if _titles_clash(title, history):
        return None, f"repeats an existing topic: {title}"
    if not why:
        return None, f"{title} is missing why it fits the saved words"
    blob = " ".join([title, why, *prompts])
    scene = _forbidden_hit(blob, forbidden_ids)
    if scene:
        return None, (
            f"{title} uses a generic scene ({scene_label(scene)}) "
            "that the saved words do not support"
        )
    learning = normalize_language(language)
    if learning == "japanese" and _LEVANTINE.search(blob):
        return None, f"{title} uses Levantine Arabizi instead of Japanese"
    if learning == "arabic" and _JAPANESE_SCRIPT.search(" ".join(prompts)):
        return None, f"{title} uses Japanese in the starter lines"
    raw_words = item.get("target_words")
    if not isinstance(raw_words, list):
        raw_words = []
    resolved = []
    seen: set[int] = set()
    for entry in raw_words:
        word = _resolve_word(entry, index)
        if word is None or word["id"] in seen:
            continue
        seen.add(word["id"])
        resolved.append(word)
        if len(resolved) == MAX_TARGET_WORDS:
            break
    if len(resolved) < MIN_TARGET_WORDS:
        return None, f"{title} does not cite enough saved words"
    return (
        {
            "title": title,
            "why": why,
            "prompts": prompts,
            "target_words": resolved,
        },
        "",
    )


def accept_generated(
    raw: dict,
    library: list[dict],
    support_words: list[dict],
    history: list[dict],
    language: str,
) -> tuple[list[dict], list[str], bool]:
    """Keep topics that cite real saved words and avoid forbidden scenes.

    Returns accepted topics (primary first), repair notes, and whether the
    model's first topic survived as the primary.
    """
    incoming = _raw_topics(raw)[:MAX_TOPICS]
    if not incoming:
        return [], ["model returned no topics"], False
    index = _library_index(library)
    forbidden_ids = forbidden_scene_ids(support_words)
    accepted: list[dict] = []
    problems: list[str] = []
    primary_ok = False
    for position, item in enumerate(incoming):
        topic, problem = _screen_topic(item, index, forbidden_ids, history, language)
        if topic is None:
            if problem:
                problems.append(problem)
            continue
        if position == 0:
            primary_ok = True
        # Drop a later topic that repeats one we just accepted.
        if _titles_clash(topic["title"], accepted):
            problems.append(f"repeats an existing topic: {topic['title']}")
            if position == 0:
                primary_ok = False
            continue
        accepted.append(topic)
    if not accepted and not problems:
        problems.append("model returned no topics")
    return accepted, problems, primary_ok and bool(accepted)


def _repair_prompt(prompt: str, problems: list[str]) -> str:
    notes = "\n".join(f"- {problem}" for problem in problems) or "- model returned no topics"
    return (
        prompt
        + "\nIMPORTANT CORRECTION:\n"
        + "The previous JSON was rejected:\n"
        + notes
        + "\nWrite a new JSON. Use only saved spellings. "
        + "Do not use a forbidden scene. Do not repeat a title already used.\n"
    )


def _row_topic(row) -> dict:
    try:
        payload = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        words = json.loads(row["target_words"] or "[]")
    except json.JSONDecodeError:
        words = []
    if not isinstance(words, list):
        words = []
    prompts = payload.get("prompts") if isinstance(payload.get("prompts"), list) else []
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "status": row["status"],
        "why": str(payload.get("why") or ""),
        "prompts": [str(line) for line in prompts if str(line).strip()],
        "target_words": words,
        "role": payload.get("role") if payload.get("role") in ("primary", "alternate") else "",
        "created_at": row["created_at"],
        "language": row["language"],
    }


def list_topics(
    conn,
    user_id: str = LOCAL_USER,
    language: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Newest topics for this account and learning language."""
    learning = normalize_language(language or get_language(conn, user_id))
    cleaned = (status or "").strip()
    if cleaned and cleaned not in STATUSES:
        raise ValueError("status must be suggested, done, or skipped")
    sql = (
        "SELECT id, title, status, target_words, payload, created_at, language "
        "FROM lesson_topics WHERE user_id = ? AND language = ?"
    )
    params: list = [user_id, learning]
    if cleaned:
        sql += " AND status = ?"
        params.append(cleaned)
    sql += " ORDER BY created_at DESC, id ASC LIMIT ?"
    params.append(LIST_LIMIT)
    rows = conn.execute(sql, params).fetchall()
    return [_row_topic(row) for row in rows]


def set_topic_status(
    conn,
    topic_id: int,
    status: str,
    user_id: str = LOCAL_USER,
    language: str | None = None,
) -> dict:
    """Mark a topic done, skipped, or back to suggested. Scoped to the owner."""
    cleaned = (status or "").strip()
    if cleaned not in STATUSES:
        raise ValueError("status must be suggested, done, or skipped")
    learning = normalize_language(language or get_language(conn, user_id))
    try:
        topic_id = int(topic_id)
    except (TypeError, ValueError):
        raise LookupError("no topic") from None
    row = conn.execute(
        "SELECT id FROM lesson_topics WHERE id = ? AND user_id = ? AND language = ?",
        (topic_id, user_id, learning),
    ).fetchone()
    if row is None:
        raise LookupError("no topic")
    with conn:
        conn.execute(
            "UPDATE lesson_topics SET status = ? WHERE id = ?",
            (cleaned, topic_id),
        )
    updated = conn.execute(
        "SELECT id, title, status, target_words, payload, created_at, language "
        "FROM lesson_topics WHERE id = ?",
        (topic_id,),
    ).fetchone()
    return _row_topic(updated)


def _insert_topics(conn, topics: list[dict], user_id: str, language: str) -> list[dict]:
    stamp = datetime.now(timezone.utc)
    saved = []
    with conn:
        for index, topic in enumerate(topics[:MAX_TOPICS]):
            role = "primary" if index == 0 else "alternate"
            payload = {
                "title": topic["title"],
                "why": topic["why"],
                "prompts": topic["prompts"],
                "target_words": topic["target_words"],
                "role": role,
            }
            created_at = (stamp - timedelta(milliseconds=index * 10)).isoformat()
            topic_id = insert_id(
                conn,
                """
                INSERT INTO lesson_topics (
                    user_id, language, title, status, target_words, payload, created_at
                ) VALUES (?, ?, ?, 'suggested', ?, ?, ?)
                """,
                (
                    user_id,
                    language,
                    topic["title"],
                    json.dumps(topic["target_words"], ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                ),
            )
            saved.append(
                {
                    "id": topic_id,
                    "title": topic["title"],
                    "status": "suggested",
                    "why": topic["why"],
                    "prompts": list(topic["prompts"]),
                    "target_words": list(topic["target_words"]),
                    "role": role,
                    "created_at": created_at,
                    "language": language,
                }
            )
    return saved


def generate_topics(
    conn,
    api_key: str,
    opener=None,
    pace: RateLimiter | None = None,
    user_id: str = LOCAL_USER,
    language: str | None = None,
) -> dict:
    """Ask for one primary topic and alternates, then store them as suggested.

    A generic tourist scene, invented spelling, or repeated title is rejected
    and the model is asked once more.
    """
    if opener is None:
        import urllib.request

        opener = urllib.request.urlopen
    if pace is None:
        pace = _TOPIC_PACE
    learning = normalize_language(language or get_language(conn, user_id))
    drop_exact_duplicates(conn, user_id=user_id, language=learning)
    library = list_items(conn, user_id=user_id, language=learning)
    unique = _unique_items(library)
    if len(unique) < MIN_SAVED_WORDS:
        raise ValueError("save a few words first")
    sample = select_topic_words(library)
    support = newest_support_words(library)
    history = list_topics(conn, user_id=user_id, language=learning)
    prompt = build_topic_prompt(sample, history, learning, support_words=support)

    def ask(text: str) -> tuple[list[dict], list[str], bool]:
        try:
            raw = _topic_model_json(text, api_key, opener, pace)
        except json.JSONDecodeError as exc:
            raise ValueError("model returned no topics") from exc
        return accept_generated(raw, library, support, history, learning)

    try:
        accepted, problems, primary_ok = ask(prompt)
    except ValueError:
        accepted, problems, primary_ok = [], ["model returned no topics"], False
    if not primary_ok:
        # One repair pass. If that pass is empty, keep any alternates that
        # already cited real words so a bad primary does not wipe them.
        fallback = accepted
        try:
            repaired, _problems, _ok = ask(_repair_prompt(prompt, problems))
        except ValueError:
            repaired = []
        accepted = repaired or fallback
    if not accepted:
        raise ValueError("could not make a topic from your words — try again")
    saved = _insert_topics(conn, accepted, user_id, learning)
    return {
        "language": learning,
        "primary": saved[0],
        "alternates": saved[1:],
    }
