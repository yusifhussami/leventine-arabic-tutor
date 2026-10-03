"""Store dated lessons and find glosses that mean similar things."""

from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone

from lexicon.intake import item_kind, parse_lesson_text
from lexicon.judge import (
    MODEL,
    RateLimiter,
    _json_body,
    call_model,
    complete,
    message_text,
    read_api_key,
)
from lexicon.db import LOCAL_USER, insert_id
from lexicon.load import normalize_meaning, normalize_word, parse_vocabulary_csv
from lexicon.lessons import parse_date_added
from lexicon.practice import PracticeCard, PracticeSession, _oriented
from lexicon.prefs import (
    DEFAULT_LANGUAGE,
    get_language,
    metalanguage_label,
    writing_system,
    writing_system_label,
)
from lexicon.prompt import build_prompt
from lexicon.speak import arabic_for_speech

EMBED_MODEL = "openai/text-embedding-3-small"
EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
_EMBED_PACE = RateLimiter()
_IMPORT_MARK = "imported from vocabulary.csv"
_BATCH = 64


def _known_pairs(conn, user_id: str = LOCAL_USER) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return {(normalize_word(row["spelling"]), normalize_meaning(row["gloss"])) for row in rows}


def drop_exact_duplicates(conn, user_id: str = LOCAL_USER) -> int:
    """Keep the newest copy of a spelling with the same meaning. Other glosses stay."""
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ?
        ORDER BY l.learned_on DESC, l.id DESC, i.id DESC
        """,
        (user_id,),
    ).fetchall()
    seen: set[tuple[str, str]] = set()
    remove: list[int] = []
    for row in rows:
        key = (normalize_word(row["spelling"]), normalize_meaning(row["gloss"]))
        if not key[0]:
            continue
        if key in seen:
            remove.append(row["id"])
        else:
            seen.add(key)
    if remove:
        with conn:
            conn.executemany("DELETE FROM lesson_items WHERE id = ?", [(item_id,) for item_id in remove])
    return len(remove)


def save_lesson(
    conn,
    learned_on: str,
    raw_text: str,
    embed=None,
    user_id: str = LOCAL_USER,
) -> dict:
    """Parse the paste, store the lesson, and attach a gloss vector when one exists.

    A spelling with the same meaning as one already saved is not stored again.
    """
    parsed = [(spelling, gloss) for spelling, gloss in parse_lesson_text(raw_text)]
    known = _known_pairs(conn, user_id)
    pairs = []
    skipped = []
    for spelling, gloss in parsed:
        key = (normalize_word(spelling), normalize_meaning(gloss))
        if not key[0] or key in known:
            skipped.append({"spelling": spelling, "gloss": gloss})
            continue
        known.add(key)
        pairs.append((spelling, gloss))
    if not pairs:
        names = ", ".join(item["spelling"] for item in skipped)
        raise ValueError(f"already saved: {names}")
    if embed is None:
        embed = embed_glosses
    try:
        vectors = embed([gloss for _, gloss in pairs])
    except Exception:
        vectors = [None] * len(pairs)
    if vectors is None or len(vectors) != len(pairs):
        vectors = [None] * len(pairs)

    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        lesson_id = insert_id(
            conn,
            "INSERT INTO lessons (user_id, learned_on, raw_text, created_at) VALUES (?, ?, ?, ?)",
            (user_id, learned_on, raw_text.strip(), created_at),
        )
        items = []
        for position, (spelling, gloss) in enumerate(pairs):
            item_id = insert_id(
                conn,
                """
                INSERT INTO lesson_items (lesson_id, position, spelling, gloss, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lesson_id, position, spelling, gloss, item_kind(spelling)),
            )
            vector = vectors[position]
            if vector:
                conn.execute(
                    """
                    INSERT INTO lesson_embeddings (item_id, model, vector)
                    VALUES (?, ?, ?)
                    """,
                    (item_id, EMBED_MODEL, json.dumps(vector)),
                )
            items.append(
                {
                    "id": item_id,
                    "spelling": spelling,
                    "gloss": gloss,
                    "kind": item_kind(spelling),
                }
            )
    return {"id": lesson_id, "learned_on": learned_on, "items": items, "skipped": skipped}


def import_sheet(conn, embed=None, user_id: str = LOCAL_USER) -> dict:
    """Copy practice words from the CSV table into dated lessons.

    Exact re-imports are skipped. A second run does not add the same day again.
    Local SQLite only: the hosted Postgres store has no entries table.
    """
    if embed is None:
        embed = embed_glosses
    skip = {
        row["id"]
        for row in conn.execute(
            """
            SELECT e.id
            FROM duplicate_members m
            JOIN duplicate_groups g ON g.id = m.group_id
            JOIN entries e ON e.id = m.entry_id
            WHERE g.kind = 'exact_copy'
            AND e.source_row > (
                SELECT MIN(e2.source_row)
                FROM duplicate_members m2
                JOIN entries e2 ON e2.id = m2.entry_id
                WHERE m2.group_id = g.id
            )
            """
        )
    }
    by_day: dict[str, list[tuple[str, str, str]]] = {}
    rows = conn.execute(
        """
        SELECT id, source_row, word, category, date_added, imperative, meaning, status
        FROM entries
        ORDER BY source_row
        """
    ).fetchall()
    for row in rows:
        if row["id"] in skip:
            continue
        oriented = _oriented(row)
        if oriented is None or oriented[0] not in ("word", "phrase"):
            continue
        kind, spelling, gloss = oriented
        day = parse_date_added(row["date_added"]).date().isoformat()
        by_day.setdefault(day, []).append((spelling, gloss, kind))
    return _commit_imported_days(conn, by_day, embed, user_id)


def import_csv(
    conn,
    csv_text: str,
    embed=None,
    user_id: str = LOCAL_USER,
    default_day: str | None = None,
) -> dict:
    """Turn an uploaded vocabulary CSV into dated notebook lessons.

    Works without the local entries table, so a new account on Vercel can import
    a sheet the same way. Exact spelling+meaning pairs already saved are skipped.
    Grammar notes and blank rows are ignored. Reversed Word/Meaning columns are
    swapped the same way as the older sheet import.
    """
    if embed is None:
        embed = embed_glosses
    fallback = (default_day or datetime.now(timezone.utc).date().isoformat()).strip()
    if len(fallback) != 10:
        raise ValueError("default day must be YYYY-MM-DD")
    known = _known_pairs(conn, user_id)
    seen: set[tuple[str, str]] = set()
    by_day: dict[str, list[tuple[str, str, str]]] = {}
    for row in parse_vocabulary_csv(csv_text):
        oriented = _oriented(row)
        if oriented is None or oriented[0] not in ("word", "phrase"):
            continue
        kind, spelling, gloss = oriented
        key = (normalize_word(spelling), normalize_meaning(gloss))
        if not key[0] or key in known or key in seen:
            continue
        seen.add(key)
        day = _csv_day(row.get("date_added") or "", fallback)
        by_day.setdefault(day, []).append((spelling, gloss, kind))
    if not by_day:
        raise ValueError("no new words found in that CSV")
    added = 0
    for day, triples in by_day.items():
        added += _store_imported_day(conn, day, triples, embed, user_id)
    return {"days": len(by_day), "items": added}


def _csv_day(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    try:
        return parse_date_added(text).date().isoformat()
    except ValueError:
        pass
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    raise ValueError(f"unrecognized date: {text!r}")


def _commit_imported_days(conn, by_day, embed, user_id: str) -> dict:
    added = 0
    days = 0
    for day, triples in by_day.items():
        exists = conn.execute(
            "SELECT id FROM lessons WHERE user_id = ? AND learned_on = ? AND raw_text = ?",
            (user_id, day, _IMPORT_MARK),
        ).fetchone()
        if exists:
            continue
        days += 1
        added += _store_imported_day(conn, day, triples, embed, user_id)
    return {"days": days, "items": added}


def _store_imported_day(conn, day: str, triples, embed, user_id: str = LOCAL_USER) -> int:
    spellings = [(spelling, gloss, kind) for spelling, gloss, kind in triples]
    vectors: list[list[float] | None] = []
    glosses = [gloss for _, gloss, _ in spellings]
    for start in range(0, len(glosses), _BATCH):
        chunk = glosses[start : start + _BATCH]
        try:
            vectors.extend(embed(chunk))
        except Exception:
            vectors.extend([None] * len(chunk))
    if len(vectors) != len(spellings):
        vectors = [None] * len(spellings)
    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        lesson_id = insert_id(
            conn,
            "INSERT INTO lessons (user_id, learned_on, raw_text, created_at) VALUES (?, ?, ?, ?)",
            (user_id, day, _IMPORT_MARK, created_at),
        )
        for position, ((spelling, gloss, kind), vector) in enumerate(zip(spellings, vectors)):
            item_id = insert_id(
                conn,
                """
                INSERT INTO lesson_items (lesson_id, position, spelling, gloss, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lesson_id, position, spelling, gloss, kind),
            )
            if vector:
                conn.execute(
                    "INSERT INTO lesson_embeddings (item_id, model, vector) VALUES (?, ?, ?)",
                    (item_id, EMBED_MODEL, json.dumps(vector)),
                )
    return len(spellings)


def search_items(conn, query: str, embed=None, limit: int = 40, user_id: str = LOCAL_USER) -> list[dict]:
    """Spelling hits first, then glosses close in meaning to an English query."""
    needle = _fold(query)
    if len(needle) < 2:
        return list_items(conn, user_id=user_id)
    items = list_items(conn, user_id=user_id)
    hits = []
    seen = set()
    arabizi = any(char in "2356789" for char in needle)
    for item in items:
        spelling = _fold(item["spelling"])
        gloss = _fold(item["gloss"])
        if needle in spelling or (not arabizi and needle in gloss):
            found = dict(item)
            found["match"] = "spelling" if needle in spelling else "meaning"
            hits.append(found)
            seen.add(item["id"])
            if len(hits) >= limit:
                return hits
    if arabizi or embed is False:
        return hits
    if embed is None:
        embed = embed_glosses
    try:
        vector = embed([query])[0]
    except Exception:
        return hits
    stored = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, l.learned_on, l.id AS lesson_id, e.vector
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        JOIN lesson_embeddings e ON e.item_id = i.id
        WHERE l.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    ranked = []
    for row in stored:
        if row["id"] in seen:
            continue
        score = cosine(vector, json.loads(row["vector"]))
        if score < 0.45:
            continue
        ranked.append((score, row))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    for score, row in ranked[: limit - len(hits)]:
        hits.append(
            {
                "id": row["id"],
                "spelling": row["spelling"],
                "gloss": row["gloss"],
                "kind": row["kind"],
                "learned_on": row["learned_on"],
                "lesson_id": row["lesson_id"],
                "match": "meaning",
                "score": round(score, 3),
            }
        )
    return hits


def _fold(text: str) -> str:
    folded = text.strip().casefold().replace("’", "'").replace("‘", "'")
    return " ".join(folded.split())


def list_items(conn, user_id: str = LOCAL_USER) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, l.learned_on, l.id AS lesson_id
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ?
        ORDER BY l.learned_on DESC, l.id DESC, i.position
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_item(
    conn,
    item_id: int,
    spelling: str,
    gloss: str,
    embed=None,
    user_id: str = LOCAL_USER,
) -> dict:
    """Replace one saved spelling and gloss. A new gloss gets a new vector."""
    spelling = spelling.strip()
    gloss = gloss.strip()
    if not spelling or not gloss:
        raise ValueError("need a word and a meaning")
    current = conn.execute(
        """
        SELECT i.id, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id = ? AND l.user_id = ?
        """,
        (item_id, user_id),
    ).fetchone()
    if current is None:
        raise LookupError(f"no item {item_id}")
    key = (normalize_word(spelling), normalize_meaning(gloss))
    for other in conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id != ? AND l.user_id = ?
        """,
        (item_id, user_id),
    ):
        if (normalize_word(other["spelling"]), normalize_meaning(other["gloss"])) == key:
            raise ValueError("that word is already saved")
    kind = item_kind(spelling)
    vector = None
    if current["gloss"] != gloss:
        if embed is None:
            embed = embed_glosses
        try:
            vectors = embed([gloss])
        except Exception:
            vectors = None
        if vectors and len(vectors) == 1 and vectors[0]:
            vector = vectors[0]
    with conn:
        conn.execute(
            "UPDATE lesson_items SET spelling = ?, gloss = ?, kind = ? WHERE id = ?",
            (spelling, gloss, kind, item_id),
        )
        if vector:
            conn.execute(
                """
                INSERT INTO lesson_embeddings (item_id, model, vector)
                VALUES (?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    model = excluded.model,
                    vector = excluded.vector
                """,
                (item_id, EMBED_MODEL, json.dumps(vector)),
            )
    row = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, l.learned_on, l.id AS lesson_id
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id = ? AND l.user_id = ?
        """,
        (item_id, user_id),
    ).fetchone()
    return dict(row)


def similar_items(conn, item_id: int, limit: int = 5, user_id: str = LOCAL_USER) -> list[dict]:
    """Nearest other glosses by cosine similarity. Items without a vector are skipped."""
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, e.vector
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        JOIN lesson_embeddings e ON e.item_id = i.id
        WHERE l.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    target = None
    others = []
    for row in rows:
        vector = json.loads(row["vector"])
        record = {
            "id": row["id"],
            "spelling": row["spelling"],
            "gloss": row["gloss"],
            "kind": row["kind"],
        }
        if row["id"] == item_id:
            target = vector
        else:
            others.append((record, vector))
    if target is None:
        return []
    ranked = sorted(
        ((cosine(target, vector), record) for record, vector in others),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [{**record, "score": round(score, 3)} for score, record in ranked[:limit] if score >= 0.45]


def judge_saved_item(
    conn,
    item_id: int,
    sentence: str,
    api_key: str,
    opener=urllib.request.urlopen,
    user_id: str = LOCAL_USER,
    language: str | None = None,
) -> dict:
    """Judge a sentence for one saved item and keep the reply on that item."""
    row = conn.execute(
        """
        SELECT i.id, i.lesson_id, i.spelling, i.gloss, i.kind
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id = ? AND l.user_id = ?
        """,
        (item_id, user_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"no item {item_id}")
    text = sentence.strip()
    if not text:
        raise ValueError("sentence is empty")

    target = PracticeCard(row["id"], row["kind"], row["spelling"], row["gloss"])
    cards = [target]
    siblings = conn.execute(
        """
        SELECT id, spelling, gloss, kind
        FROM lesson_items
        WHERE lesson_id = ? AND id != ?
        ORDER BY position
        """,
        (row["lesson_id"], item_id),
    ).fetchall()
    for other in list(siblings) + similar_items(conn, item_id, user_id=user_id):
        card = PracticeCard(other["id"], other["kind"], other["spelling"], other["gloss"])
        if card not in cards:
            cards.append(card)
    metalanguage = language or get_language(conn, user_id)
    uses_target, fits_meaning, comment = call_model(
        build_prompt(
            PracticeSession(tuple(cards), ()),
            target,
            text,
            language=metalanguage,
        ),
        api_key,
        opener,
    )
    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        attempt_id = insert_id(
            conn,
            "INSERT INTO lesson_attempts (item_id, sentence, created_at) VALUES (?, ?, ?)",
            (item_id, text, created_at),
        )
        conn.execute(
            """
            INSERT INTO lesson_judgments (
                attempt_id, model, uses_target, fits_meaning, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                MODEL,
                int(uses_target),
                int(fits_meaning),
                comment,
                created_at,
            ),
        )
    return {
        "uses_target": uses_target,
        "fits_meaning": fits_meaning,
        "comment": comment,
        "similar": similar_items(conn, item_id, user_id=user_id),
    }


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


_TALK_SCHEMA = {
    "type": "object",
    "properties": {
        "you_arabizi": {"type": "string"},
        "you_english": {"type": "string"},
        "arabic": {"type": "string"},
        "arabizi": {"type": "string"},
        "english": {"type": "string"},
        "correction": {"type": "string"},
        "better": {"type": "string"},
    },
    "required": [
        "you_arabizi",
        "you_english",
        "arabic",
        "arabizi",
        "english",
        "correction",
        "better",
    ],
    "additionalProperties": False,
}
_TALK_WORDS = 180
_SCENES = {
    "arabizi": {
        "coffee": (
            "You are the person at the counter of a coffee shop. The learner is ordering.\n"
            "Stay in that scene. Help them order a drink, then sweet or without sugar, large or small, and the price.\n"
            "Use these spellings: ahwe, baddi, 7elo, bala sukkar, kbeer, zgheer, 8addeesh.\n"
            "Ask only one of those in a turn, the way a real counter does. If they miss it or say it awkwardly, put the useful line in better.\n"
        ),
        "restaurant": (
            "You are the server in a restaurant. The learner is ordering food.\n"
            "Stay in that scene. Help them ask for a dish, without spice, extra, and the bill.\n"
            "Use these spellings: baddi, bala 7ar, extra, el 7seb.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
        "shop": (
            "You are the shopkeeper. The learner wants to buy something.\n"
            "Stay in that scene. Help them point to an item, ask the price, and ask for a cheaper one.\n"
            "Use these spellings: hayda, 8addeesh, ar5as.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
        "taxi": (
            "You are the taxi driver. The learner is a passenger.\n"
            "Stay in that scene. Help them name the destination, ask the price, and say stop here.\n"
            "Use these spellings: 3a, 8addeesh, wa22ef hon.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
    },
    "romaji": {
        "coffee": (
            "You are the person at the counter of a coffee shop. The learner is ordering.\n"
            "Stay in that scene. Help them order a drink, then sweet or without sugar, large or small, and the price.\n"
            "Use these romaji spellings: ahwe, baddi, helo, bala sukkar, kbeer, zgheer, qaddeesh.\n"
            "Ask only one of those in a turn, the way a real counter does. If they miss it or say it awkwardly, put the useful line in better.\n"
        ),
        "restaurant": (
            "You are the server in a restaurant. The learner is ordering food.\n"
            "Stay in that scene. Help them ask for a dish, without spice, extra, and the bill.\n"
            "Use these romaji spellings: baddi, bala har, extra, el hseb.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
        "shop": (
            "You are the shopkeeper. The learner wants to buy something.\n"
            "Stay in that scene. Help them point to an item, ask the price, and ask for a cheaper one.\n"
            "Use these romaji spellings: hayda, qaddeesh, arkhas.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
        "taxi": (
            "You are the taxi driver. The learner is a passenger.\n"
            "Stay in that scene. Help them name the destination, ask the price, and say stop here.\n"
            "Use these romaji spellings: 'a, qaddeesh, wa''ef hon.\n"
            "Ask only one thing per turn. If they miss it, put the useful line in better.\n"
        ),
    },
}


def talk(
    conn,
    turns: list,
    api_key: str,
    opener=None,
    pace=None,
    scene: str = "",
    user_id: str = LOCAL_USER,
    language: str | None = None,
) -> dict:
    """One short Levantine reply that prefers words already saved.

    The newest saved words are the ones the model sees, so a turn stays small.
    Arabic script is for Sawt's speech. English accounts speak/type Arabizi;
    Japanese accounts may speak Japanese, and see romaji on the page.
    """
    history = _talk_turns(turns)
    drop_exact_duplicates(conn, user_id=user_id)
    metalanguage = language or get_language(conn, user_id)
    if metalanguage not in ("en", "ja"):
        metalanguage = DEFAULT_LANGUAGE
    system = writing_system(metalanguage)
    latin = writing_system_label(metalanguage)
    seen: set[str] = set()
    chosen = []
    for item in list_items(conn, user_id=user_id):
        key = normalize_word(item["spelling"])
        if not key or key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) == _TALK_WORDS:
            break
    if not chosen:
        raise ValueError("save a few words first")
    vocab = "\n".join(f"{item['spelling']} = {item['gloss']}" for item in chosen)
    spoken = "\n".join(f"{turn['role']}: {turn['text']}" for turn in history)
    scenes = _SCENES[system]
    scene_block = f"\n{scenes[scene]}\n" if scene in scenes else "\n"
    prompt = (
        "You are a Levantine friend on a voice call, not a teacher giving a lesson.\n"
        "Answer in one or two short spoken sentences, the way people actually talk.\n"
        "Prefer the learner's saved words when they fit. Each spelling is listed once.\n"
        "Do not repeat a line you already said in this conversation. Do not quiz them.\n"
        f"{_talk_spelling_block(system)}"
        f"{_talk_learner_input_block(metalanguage, latin)}"
        "arabic is ONLY Arabic Unicode script for text-to-speech — letters like مرحبا كيفك.\n"
        "Never put romaji, Arabizi digits, English, or Japanese in arabic. TTS reads that field aloud.\n"
        f"arabizi is your spoken reply in {latin} (field name is historical).\n"
        f"{_talk_metalanguage_block(metalanguage, latin)}"
        "If the latest user line begins with Start or スタート, you speak first in the scene and leave you_arabizi and you_english empty.\n"
        f"{_talk_correction_block(metalanguage, latin)}"
        + scene_block
        + "Saved words, newest first:\n"
        f"{vocab}\n"
        "\n"
        "Conversation:\n"
        f"{spoken}\n"
    )
    body = _json_body(prompt, "reply", _TALK_SCHEMA, temperature=0.4)
    body["max_tokens"] = 280
    if opener is None:
        opener = urllib.request.urlopen
    payload = complete(body, api_key, opener, pace=pace)
    data = json.loads(message_text(payload))
    arabic = str(data["arabic"]).strip()
    try:
        arabic = arabic_for_speech(arabic)
    except ValueError:
        # Keep empty so the page can fall back to typing; never send romaji to TTS.
        arabic = ""
    return {
        "you_arabizi": str(data["you_arabizi"]).strip(),
        "you_english": str(data["you_english"]).strip(),
        "arabic": arabic,
        "arabizi": str(data["arabizi"]).strip(),
        "english": str(data["english"]).strip(),
        "correction": str(data["correction"]).strip(),
        "better": str(data["better"]).strip(),
    }


def _talk_spelling_block(system: str) -> str:
    """Latin spelling rules. Arabic script for speech is separate."""
    if system == "romaji":
        return (
            "Spell Levantine in romaji (ローマ字), lowercase, the way a Japanese learner writes Arabic sounds in Latin letters.\n"
            "Copy a saved word exactly when you use it.\n"
            "Do not use Arabizi digit letters (2, 3, 5, 6, 7, 8, 9).\n"
            "Use ' for ء/أ and ع, gh for غ, kh for خ, t for ط, h for ح, q for ق, s for ص, d for ض.\n"
            "Write long ee as ee and long oo as oo. كيفك is keefak, never kayfak or kifak.\n"
            "مرحبا is marhaba (not mar7aba). قديش is qaddeesh (not 8addeesh).\n"
        )
    return (
        "Spell Arabizi the way this notebook does, lowercase, and copy a saved word exactly when you use it.\n"
        "2 is ء or أ, 3 is ع, 3' is غ, 5 is خ, 6 is ط, 7 is ح, 8 is ق, 9 is ص, 9' is ض.\n"
        "Write long ee as ee and long oo as oo. كيفك is keefak, never kayfak or kifak.\n"
    )


def _talk_learner_input_block(language: str, latin: str) -> str:
    """How to read the learner's mic/typed line for this account language."""
    if language == "ja":
        return (
            "The learner often speaks Japanese into the mic. They may also type Japanese or Levantine romaji.\n"
            "Understand Japanese naturally and answer as a friend in Levantine — do not answer in Japanese speech.\n"
            "If their latest line is Japanese (hiragana, katakana, or kanji):\n"
            "  you_english = clean Japanese for what they meant\n"
            f"  you_arabizi = natural Levantine {latin} for how to say that meaning (so they learn the line)\n"
            "If their latest line is already Levantine romaji, you_arabizi is that line in this notebook's spelling,\n"
            "and you_english is its Japanese gloss.\n"
        )
    return (
        f"you_arabizi is what the learner just said, in {latin}. No Arabic script there.\n"
        "you_english is a plain English translation of that line.\n"
    )


def _talk_correction_block(language: str, latin: str) -> str:
    if language == "ja":
        return (
            "If they spoke Japanese, leave correction empty; you_arabizi already teaches the Levantine line.\n"
            f"You may set better to that same {latin} line. If they tried Levantine romaji and it was off,\n"
            "set correction to one kind Japanese sentence about what was off, and better to a fuller "
            f"{latin} line. If it was fine, leave both empty.\n"
        )
    return (
        "If their Levantine is off, set correction to one kind sentence about what was off,\n"
        f"and better to a fuller way they could say it, in {latin}. If it was fine, leave both empty.\n"
    )


def _talk_metalanguage_block(language: str, latin: str) -> str:
    """Instructions for page glosses. Latin spelling and Arabic script stay Levantine."""
    label = metalanguage_label(language)
    return (
        f"The learner's metalanguage is {label}.\n"
        f"you_english and english are plain {label} for the page "
        "(the field names say english for historical reasons).\n"
        f"correction, when set, is also {label}.\n"
        f"Never put Japanese or English into you_arabizi, arabizi, or better — those stay {latin}.\n"
        "arabic stays Arabic script only, for Sawt's speech out.\n"
    )


def _talk_turns(turns: list) -> list[dict]:
    if not isinstance(turns, list) or not turns:
        raise ValueError("say something first")
    history = []
    for turn in turns[-6:]:
        if not isinstance(turn, dict):
            raise ValueError("say something first")
        role = turn.get("role")
        text = str(turn.get("text") or "").strip()
        if role not in ("user", "assistant") or not text:
            raise ValueError("say something first")
        history.append({"role": role, "text": text[:400]})
    if history[-1]["role"] != "user":
        raise ValueError("say something first")
    return history


def embed_glosses(glosses: list[str], opener=urllib.request.urlopen) -> list[list[float]]:
    """Embed English glosses in one request. Arabizi is not what gets compared."""
    _EMBED_PACE.wait()
    request = urllib.request.Request(
        EMBED_URL,
        data=json.dumps(
            {"model": EMBED_MODEL, "input": glosses, "dimensions": 256}
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {read_api_key()}",
        },
        method="POST",
    )
    with opener(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    rows = sorted(payload["data"], key=lambda row: row.get("index", 0))
    return [row["embedding"] for row in rows]
