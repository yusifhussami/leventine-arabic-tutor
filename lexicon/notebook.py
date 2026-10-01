"""Store dated lessons and find glosses that mean similar things."""

from __future__ import annotations

import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timezone

from lexicon.intake import item_kind, parse_lesson_text
from lexicon.judge import MODEL, RateLimiter, call_model, read_api_key
from lexicon.practice import PracticeCard, PracticeSession
from lexicon.prompt import build_prompt

EMBED_MODEL = "openai/text-embedding-3-small"
EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
_EMBED_PACE = RateLimiter()


def save_lesson(
    conn: sqlite3.Connection,
    learned_on: str,
    raw_text: str,
    embed=None,
) -> dict:
    """Parse the paste, store the lesson, and attach a gloss vector when one exists."""
    pairs = [(spelling, gloss) for spelling, gloss in parse_lesson_text(raw_text)]
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
        cursor = conn.execute(
            "INSERT INTO lessons (learned_on, raw_text, created_at) VALUES (?, ?, ?)",
            (learned_on, raw_text.strip(), created_at),
        )
        lesson_id = int(cursor.lastrowid)
        items = []
        for position, (spelling, gloss) in enumerate(pairs):
            item_cursor = conn.execute(
                """
                INSERT INTO lesson_items (lesson_id, position, spelling, gloss, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lesson_id, position, spelling, gloss, item_kind(spelling)),
            )
            item_id = int(item_cursor.lastrowid)
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
    return {"id": lesson_id, "learned_on": learned_on, "items": items}


def list_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, l.learned_on, l.id AS lesson_id
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        ORDER BY l.learned_on DESC, l.id DESC, i.position
        """
    ).fetchall()
    return [dict(row) for row in rows]


def similar_items(conn: sqlite3.Connection, item_id: int, limit: int = 5) -> list[dict]:
    """Nearest other glosses by cosine similarity. Items without a vector are skipped."""
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss, i.kind, e.vector
        FROM lesson_items i
        JOIN lesson_embeddings e ON e.item_id = i.id
        """
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
    conn: sqlite3.Connection,
    item_id: int,
    sentence: str,
    api_key: str,
    opener=urllib.request.urlopen,
) -> dict:
    """Judge a sentence for one saved item and keep the reply on that item."""
    row = conn.execute(
        """
        SELECT id, lesson_id, spelling, gloss, kind
        FROM lesson_items
        WHERE id = ?
        """,
        (item_id,),
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
    for other in list(siblings) + similar_items(conn, item_id):
        card = PracticeCard(other["id"], other["kind"], other["spelling"], other["gloss"])
        if card not in cards:
            cards.append(card)
    uses_target, fits_meaning, comment = call_model(
        build_prompt(PracticeSession(tuple(cards), ()), target, text),
        api_key,
        opener,
    )
    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        attempt = conn.execute(
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
                int(attempt.lastrowid),
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
        "similar": similar_items(conn, item_id),
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
