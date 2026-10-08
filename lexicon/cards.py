"""Flashcard decks: notebook words, and Anki packages kept in their own decks.

Words decks follow the language you're learning and pick up new notebook words
automatically. Anki imports stay separate. Reviews use lexicon.fsrs.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from lexicon.apkg import read_apkg
from lexicon.db import insert_id
from lexicon.fsrs import (
    LEARN_AHEAD_MINUTES,
    NEW_PER_DAY,
    format_interval,
    normalize_new_per_day,
    normalize_retention,
    normalize_weights,
    review_due,
    schedule,
    scheduler_date,
)
from lexicon.prefs import get_language

_BUTTONS = (
    (1, "Again"),
    (2, "Hard"),
    (3, "Good"),
    (4, "Easy"),
)
_WORDS_DECK_NAME = "My Words"
MAX_EXTRA_PER_DAY = 999


def list_decks(conn, user_id: str, now: datetime | None = None) -> dict:
    now = _now(now)
    language = get_language(conn, user_id)
    sync_words_for_user(conn, user_id, now=now)
    word_rows = conn.execute(
        """
        SELECT * FROM card_decks
        WHERE user_id = ? AND source = 'words' AND language = ?
        ORDER BY id ASC
        """,
        (user_id, language),
    ).fetchall()
    anki_rows = conn.execute(
        """
        SELECT * FROM card_decks
        WHERE user_id = ? AND source = 'anki'
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    return {
        "words": [_summary(conn, row, now) for row in word_rows],
        "anki": [_summary(conn, row, now) for row in anki_rows],
        "settings": _study_settings(conn, user_id),
        "has_words": _notebook_word_count(conn, user_id, language) > 0,
    }


def sync_words_for_user(conn, user_id: str, now: datetime | None = None):
    """Create the Words deck when needed and add any new notebook words."""
    now = _now(now)
    language = get_language(conn, user_id)
    if _notebook_word_count(conn, user_id, language) == 0:
        return None
    deck = _words_deck_row(conn, user_id, language)
    if deck is None:
        with conn:
            deck_id = insert_id(
                conn,
                """
                INSERT INTO card_decks (user_id, source, language, name, weights, retention, created_at)
                VALUES (?, 'words', ?, ?, '', 0.9, ?)
                """,
                (user_id, language, _WORDS_DECK_NAME, _stamp(now)),
            )
        deck = _owned_deck(conn, user_id, deck_id)
    _sync_words_deck(conn, deck, now)
    return _owned_deck(conn, user_id, deck["id"])


def create_word_deck(conn, user_id: str, name: str, item_ids, now: datetime | None = None) -> dict:
    """Open the live Words deck. Name/selection are ignored; every saved word is included."""
    now = _now(now)
    deck = sync_words_for_user(conn, user_id, now=now)
    if deck is None:
        raise ValueError("save some words first")
    if name and _name(name) != deck["name"]:
        # Keep a custom title if the caller still passes one for an empty/new deck.
        title = _name(name)
        if deck["name"] == _WORDS_DECK_NAME:
            with conn:
                conn.execute(
                    "UPDATE card_decks SET name = ? WHERE id = ? AND user_id = ?",
                    (title, deck["id"], user_id),
                )
            deck = _owned_deck(conn, user_id, deck["id"])
    ids = _item_ids(item_ids)
    if ids:
        language = deck["language"]
        added = []
        for item_id in ids:
            if _card_for_item(conn, deck["id"], item_id) is not None:
                continue
            added.append(_owned_item(conn, user_id, language, item_id))
        if added:
            with conn:
                _insert_word_cards(conn, deck["id"], added, now)
        _sync_words_deck(conn, deck, now)
    return study(conn, user_id, deck["id"], now)


def add_words(conn, user_id: str, deck_id: int, item_ids, now: datetime | None = None) -> dict:
    now = _now(now)
    deck = _owned_deck(conn, user_id, deck_id)
    if deck["source"] != "words":
        raise ValueError("imported decks stay as they were imported")
    _sync_words_deck(conn, deck, now)
    ids = _item_ids(item_ids)
    added = []
    for item_id in ids:
        if _card_for_item(conn, deck_id, item_id) is not None:
            continue
        added.append(_owned_item(conn, user_id, deck["language"], item_id))
    if added:
        with conn:
            _insert_word_cards(conn, deck_id, added, now)
    return study(conn, user_id, deck_id, now)


def remove_words(conn, user_id: str, deck_id: int, item_ids, now: datetime | None = None) -> dict:
    now = _now(now)
    deck = _owned_deck(conn, user_id, deck_id)
    if deck["source"] != "words":
        raise ValueError("imported decks stay as they were imported")
    ids = _item_ids(item_ids)
    if ids:
        marks = ",".join("?" for _ in ids)
        with conn:
            conn.execute(
                f"DELETE FROM study_cards WHERE deck_id = ? AND item_id IN ({marks})",
                (deck_id, *ids),
            )
    return study(conn, user_id, deck_id, now)


def delete_deck(conn, user_id: str, deck_id: int) -> dict:
    _owned_deck(conn, user_id, deck_id)
    with conn:
        conn.execute(
            "DELETE FROM card_decks WHERE id = ? AND user_id = ?",
            (deck_id, user_id),
        )
    return {"deleted": deck_id}


def word_choices(conn, user_id: str, deck_id: int) -> list[dict]:
    deck = _owned_deck(conn, user_id, deck_id)
    if deck["source"] != "words":
        raise ValueError("imported decks stay as they were imported")
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = ?
        ORDER BY l.learned_on DESC, l.id DESC, i.position
        """,
        (user_id, deck["language"]),
    ).fetchall()
    chosen = {
        row["item_id"]
        for row in conn.execute(
            "SELECT item_id FROM study_cards WHERE deck_id = ? AND item_id IS NOT NULL",
            (deck_id,),
        )
        if row["item_id"] is not None
    }
    return [
        {
            "id": row["id"],
            "spelling": row["spelling"],
            "gloss": row["gloss"],
            "in_deck": row["id"] in chosen,
        }
        for row in rows
    ]


def card_settings(conn, user_id: str) -> dict:
    """Study options: prompt side, timer, and Anki-style new cards per day."""
    language = get_language(conn, user_id)
    side = _card_side(conn, user_id)
    prompt, answer, example = _preview_pair(conn, user_id, language)
    if side == "meaning":
        prompt, answer = answer, prompt
    return {
        "timer": _card_timer(conn, user_id),
        "side": side,
        "new_per_day": _new_per_day(conn, user_id),
        "prompt_label": "Japanese" if language == "japanese" else "Arabic",
        "answer_label": "English",
        "preview_prompt": prompt,
        "preview_answer": answer,
        "preview_example": example,
    }


def save_card_settings(conn, user_id: str, body: dict) -> dict:
    if "timer" not in body and "side" not in body and "new_per_day" not in body:
        return card_settings(conn, user_id)
    if "timer" in body and not isinstance(body["timer"], bool):
        raise ValueError("timer is on or off")
    if "side" in body and body["side"] not in ("word", "meaning"):
        raise ValueError("show the word or the English")
    new_per_day = None
    if "new_per_day" in body:
        if isinstance(body["new_per_day"], bool):
            raise ValueError("new cards per day must be a number")
        try:
            requested = int(body["new_per_day"])
        except (TypeError, ValueError):
            raise ValueError("new cards per day must be a number") from None
        if requested < 0 or requested > 999:
            raise ValueError("new cards per day is 0–999")
        new_per_day = requested
    if "timer" in body:
        _put_setting(conn, user_id, "cards_timer", "1" if body["timer"] else "0")
    if "side" in body:
        _put_setting(conn, user_id, "cards_side", body["side"])
    if new_per_day is not None:
        _put_setting(conn, user_id, "cards_new_per_day", str(new_per_day))
    conn.commit()
    return card_settings(conn, user_id)


def study(conn, user_id: str, deck_id: int, now: datetime | None = None) -> dict:
    now = _now(now)
    deck = _owned_deck(conn, user_id, deck_id)
    if deck["source"] == "words":
        _sync_words_deck(conn, deck, now)
        deck = _owned_deck(conn, user_id, deck_id)
    queue, waiting = _queue(conn, deck, now)
    card = queue[0] if queue else None
    payload = {
        "deck": {
            "id": deck["id"],
            "name": deck["name"],
            "source": deck["source"],
        },
        "due": len(queue),
        "later": waiting["later"],
        "later_label": waiting["later_label"],
        "new_tomorrow": waiting["new_tomorrow"],
        "new_per_day": waiting["new_per_day"],
        "new_done": waiting["new_done"],
        "new_left": waiting["new_left"],
        "settings": _study_settings(conn, user_id),
        "card": None,
    }
    if card is None:
        return payload
    front, back = _faces(conn, user_id, card)
    if _card_side(conn, user_id) == "meaning":
        front, back = back, front
    buttons = schedule(card, now, _weights(deck), _retention(deck))
    payload["card"] = {
        "id": card["id"],
        "front": front,
        "back": back,
        "buttons": [
            {"rating": rating, "label": label, "interval": buttons[rating].interval_label}
            for rating, label in _BUTTONS
        ],
    }
    return payload


def answer(conn, user_id: str, deck_id: int, card_id: int, rating: int, now: datetime | None = None) -> dict:
    now = _now(now)
    if rating not in (1, 2, 3, 4):
        raise ValueError("choose Again, Hard, Good, or Easy")
    deck = _owned_deck(conn, user_id, deck_id)
    card = _card(conn, deck_id, card_id)
    if card is None:
        raise LookupError("that card is gone")
    card = _with_times(card)
    outcome = schedule(card, now, _weights(deck), _retention(deck))[rating]
    introduced = card["introduced_on"]
    if card["state"] == "new":
        introduced = scheduler_date(now).isoformat()
    due = _due_stamp(now, outcome)
    with conn:
        conn.execute(
            """
            UPDATE study_cards
            SET state = ?, stability = ?, difficulty = ?, due_at = ?, scheduled_days = ?,
                learning_remaining = ?, reps = ?, lapses = ?, last_review_at = ?,
                introduced_on = ?
            WHERE id = ? AND deck_id = ?
            """,
            (
                outcome.state,
                outcome.stability,
                outcome.difficulty,
                due,
                outcome.scheduled_days,
                outcome.learning_remaining,
                int(card["reps"] or 0) + 1,
                outcome.lapses,
                _stamp(now),
                introduced,
                card_id,
                deck_id,
            ),
        )
    return study(conn, user_id, deck_id, now)


def import_apkg(conn, blob: bytes, user_id: str, now: datetime | None = None) -> dict:
    now = _now(now)
    decks = read_apkg(blob)
    saved = []
    with conn:
        for deck in decks:
            weights = json.dumps(list(deck["weights"])) if deck["weights"] else ""
            deck_id = insert_id(
                conn,
                """
                INSERT INTO card_decks (user_id, source, language, name, weights, retention, created_at)
                VALUES (?, 'anki', '', ?, ?, ?, ?)
                """,
                (user_id, deck["name"], weights, float(deck["retention"]), _stamp(now)),
            )
            for card in deck["cards"]:
                _insert_study_card(conn, deck_id, None, card, now)
            saved.append({"id": deck_id, "name": deck["name"], "cards": len(deck["cards"])})
    return {"decks": saved, "count": len(saved)}


def dispatch_get(conn, user_id: str, deck_id: str, action: str) -> dict | list:
    if not deck_id and action == "settings":
        return card_settings(conn, user_id)
    if deck_id and action == "words":
        return word_choices(conn, user_id, int(deck_id))
    if deck_id:
        return study(conn, user_id, int(deck_id))
    return list_decks(conn, user_id)


def dispatch_post(conn, user_id: str, deck_id: str, action: str, body: dict):
    if not deck_id and action == "settings":
        return save_card_settings(conn, user_id, body)
    if action == "delete":
        return delete_deck(conn, user_id, int(deck_id))
    if action == "add":
        return add_words(conn, user_id, int(deck_id), body.get("item_ids") or [])
    if action == "remove":
        return remove_words(conn, user_id, int(deck_id), body.get("item_ids") or [])
    if action == "more":
        return learn_more(conn, user_id, int(deck_id), body.get("count", 20))
    if action == "answer":
        return answer(
            conn,
            user_id,
            int(deck_id),
            int(body["card_id"]),
            int(body["rating"]),
        )
    if deck_id:
        raise ValueError("unknown request")
    return create_word_deck(conn, user_id, body.get("name") or _WORDS_DECK_NAME, body.get("item_ids") or [])


def _summary(conn, deck, now: datetime) -> dict:
    queue, waiting = _queue(conn, deck, now)
    return {
        "id": deck["id"],
        "name": deck["name"],
        "source": deck["source"],
        "due": len(queue),
        "later_label": waiting["later_label"],
        "auto": deck["source"] == "words",
        "new_per_day": waiting["new_per_day"],
        "new_done": waiting["new_done"],
        "new_left": waiting["new_left"],
    }


def _words_deck_row(conn, user_id: str, language: str):
    return conn.execute(
        """
        SELECT * FROM card_decks
        WHERE user_id = ? AND source = 'words' AND language = ?
        ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, id ASC
        LIMIT 1
        """,
        (user_id, language, _WORDS_DECK_NAME),
    ).fetchone()


def _notebook_word_count(conn, user_id: str, language: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = ?
        """,
        (user_id, language),
    ).fetchone()
    return int(row["n"] if isinstance(row, dict) else row[0])


def _notebook_words(conn, user_id: str, language: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = ?
        ORDER BY l.learned_on ASC, l.id ASC, i.position ASC
        """,
        (user_id, language),
    ).fetchall()
    return [dict(row) for row in rows]


def _sync_words_deck(conn, deck, now: datetime) -> int:
    """Add notebook words that are not cards yet. Returns how many were added."""
    if deck["source"] != "words":
        return 0
    words = _notebook_words(conn, deck["user_id"], deck["language"])
    if not words:
        return 0
    present = {
        row["item_id"]
        for row in conn.execute(
            "SELECT item_id FROM study_cards WHERE deck_id = ? AND item_id IS NOT NULL",
            (deck["id"],),
        )
        if row["item_id"] is not None
    }
    missing = [word for word in words if word["id"] not in present]
    if not missing:
        return 0
    with conn:
        _insert_word_cards(conn, deck["id"], missing, now)
    return len(missing)


def _queue(conn, deck, now: datetime) -> tuple[list[dict], dict]:
    rows = [
        _with_times(row)
        for row in conn.execute(
            "SELECT * FROM study_cards WHERE deck_id = ? AND suspended = 0 ORDER BY id",
            (deck["id"],),
        )
    ]
    due = []
    upcoming = []
    fresh = []
    for card in rows:
        if card["state"] == "new":
            fresh.append(card)
            continue
        if card["due_at"] <= now:
            due.append(card)
        else:
            upcoming.append(card)
    due.sort(key=lambda card: (0 if card["state"] in ("learning", "relearning") else 1, card["due_at"], card["id"]))
    introduced = conn.execute(
        """
        SELECT COUNT(*) AS n FROM study_cards
        WHERE deck_id = ? AND introduced_on = ?
        """,
        (deck["id"], scheduler_date(now).isoformat()),
    ).fetchone()
    limit = _new_per_day(conn, deck["user_id"]) + _extra_today(conn, deck["user_id"], now)
    seen = int(introduced["n"] if isinstance(introduced, dict) else introduced[0])
    quota = max(0, limit - seen)
    fresh.sort(key=lambda card: card["id"])
    # Anki order: learning/review that are due, then today's new-card quota.
    queue = due + fresh[:quota]
    waiting = {
        "later": None,
        "later_label": "",
        "new_tomorrow": False,
        "new_per_day": limit,
        "new_done": seen,
        # How many new cards can still enter today's queue (limit and remaining unseen).
        "new_left": min(quota, len(fresh)),
    }
    if queue:
        return queue, waiting
    # Anki learn-ahead: if the queue is empty, pull learning cards due soon
    # instead of parking you on a 1m/10m wait screen.
    ahead_until = now + timedelta(minutes=LEARN_AHEAD_MINUTES)
    ahead = [
        card
        for card in upcoming
        if card["state"] in ("learning", "relearning") and card["due_at"] <= ahead_until
    ]
    ahead.sort(key=lambda card: (card["due_at"], card["id"]))
    if ahead:
        return ahead, waiting
    if fresh and quota == 0:
        rollover = review_due(now, 1)
        seconds = max(0, int((rollover - now).total_seconds()))
        waiting["later"] = seconds
        waiting["later_label"] = format_interval(seconds)
        waiting["new_tomorrow"] = True
        return queue, waiting
    if upcoming:
        nxt = min(card["due_at"] for card in upcoming)
        seconds = max(0, int((nxt - now).total_seconds()))
        waiting["later"] = seconds
        waiting["later_label"] = format_interval(seconds)
    return queue, waiting


def _study_settings(conn, user_id: str) -> dict:
    return {
        "timer": _card_timer(conn, user_id),
        "side": _card_side(conn, user_id),
        "new_per_day": _new_per_day(conn, user_id),
    }


def _card_timer(conn, user_id: str) -> bool:
    return _setting(conn, user_id, "cards_timer") == "1"


def _card_side(conn, user_id: str) -> str:
    side = _setting(conn, user_id, "cards_side")
    return side if side in ("word", "meaning") else "word"


def _new_per_day(conn, user_id: str) -> int:
    raw = _setting(conn, user_id, "cards_new_per_day")
    if raw == "":
        return NEW_PER_DAY
    return normalize_new_per_day(raw)


def _extra_today(conn, user_id: str, now: datetime) -> int:
    day, _, count = _setting(conn, user_id, "cards_new_extra").partition(":")
    if day != scheduler_date(now).isoformat():
        return 0
    try:
        return max(0, int(count))
    except ValueError:
        return 0


def learn_more(conn, user_id: str, deck_id: int, count, now: datetime | None = None) -> dict:
    """Anki's "increase today's new card limit": extra new cards for today only."""
    now = _now(now)
    _owned_deck(conn, user_id, deck_id)
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise ValueError("choose how many more words") from None
    if count < 1 or count > MAX_EXTRA_PER_DAY:
        raise ValueError(f"learn 1–{MAX_EXTRA_PER_DAY} more at a time")
    total = min(MAX_EXTRA_PER_DAY, _extra_today(conn, user_id, now) + count)
    _put_setting(conn, user_id, "cards_new_extra", f"{scheduler_date(now).isoformat()}:{total}")
    conn.commit()
    return study(conn, user_id, deck_id, now)


def _preview_pair(conn, user_id: str, language: str) -> tuple[str, str, bool]:
    row = conn.execute(
        """
        SELECT i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = ?
        ORDER BY l.learned_on DESC, l.id DESC, i.position
        LIMIT 1
        """,
        (user_id, language),
    ).fetchone()
    if row is not None:
        return row["spelling"], row["gloss"], False
    if language == "japanese":
        return "ねこ", "cat", True
    return "marhaba", "hello", True


def _setting(conn, user_id: str, key: str) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    return row["value"] if row else ""


def _put_setting(conn, user_id: str, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
        (user_id, key, value),
    )


def _faces(conn, user_id: str, card: dict) -> tuple[str, str]:
    if not card.get("item_id"):
        return card["front"], card["back"]
    row = conn.execute(
        """
        SELECT i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id = ? AND l.user_id = ?
        """,
        (card["item_id"], user_id),
    ).fetchone()
    if row is None:
        return card["front"], card["back"]
    return row["spelling"], row["gloss"]


def _insert_word_cards(conn, deck_id: int, words: list[dict], now: datetime) -> None:
    for word in words:
        _insert_study_card(
            conn,
            deck_id,
            word["id"],
            {
                "front": word["spelling"],
                "back": word["gloss"],
                "state": "new",
                "stability": None,
                "difficulty": None,
                "due_at": now,
                "scheduled_days": 0,
                "learning_remaining": 0,
                "reps": 0,
                "lapses": 0,
                "last_review_at": None,
                "suspended": False,
            },
            now,
        )


def _insert_study_card(conn, deck_id: int, item_id, card: dict, now: datetime) -> None:
    due = card["due_at"] if isinstance(card["due_at"], datetime) else now
    last = card.get("last_review_at")
    conn.execute(
        """
        INSERT INTO study_cards (
            deck_id, item_id, front, back, state, stability, difficulty, due_at,
            scheduled_days, learning_remaining, reps, lapses, last_review_at,
            introduced_on, suspended
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            deck_id,
            item_id,
            card["front"],
            card["back"],
            card["state"],
            card.get("stability"),
            card.get("difficulty"),
            _stamp(due),
            int(card.get("scheduled_days") or 0),
            int(card.get("learning_remaining") or 0),
            int(card.get("reps") or 0),
            int(card.get("lapses") or 0),
            _stamp(last) if isinstance(last, datetime) else None,
            None,
            1 if card.get("suspended") else 0,
        ),
    )


def _owned_deck(conn, user_id: str, deck_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM card_decks WHERE id = ? AND user_id = ?",
        (deck_id, user_id),
    ).fetchone()
    if row is None:
        raise LookupError("that deck is gone")
    return row


def _owned_item(conn, user_id: str, language: str, item_id: int) -> dict:
    row = conn.execute(
        """
        SELECT i.id, i.spelling, i.gloss
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE i.id = ? AND l.user_id = ? AND l.language = ?
        """,
        (item_id, user_id, language),
    ).fetchone()
    if row is None:
        raise ValueError("that word isn't in this notebook")
    return row


def _card_for_item(conn, deck_id: int, item_id: int):
    return conn.execute(
        "SELECT id FROM study_cards WHERE deck_id = ? AND item_id = ?",
        (deck_id, item_id),
    ).fetchone()


def _card(conn, deck_id: int, card_id: int):
    return conn.execute(
        "SELECT * FROM study_cards WHERE id = ? AND deck_id = ?",
        (card_id, deck_id),
    ).fetchone()


def _with_times(card) -> dict:
    row = dict(card)
    row["due_at"] = _parse_time(row["due_at"])
    row["last_review_at"] = _parse_time(row["last_review_at"]) if row.get("last_review_at") else None
    return row


def _weights(deck) -> tuple:
    raw = deck["weights"] if "weights" in deck.keys() else ""
    if not raw:
        return ()
    try:
        parsed = normalize_weights(json.loads(raw))
    except json.JSONDecodeError:
        return ()
    return parsed or ()


def _retention(deck) -> float:
    try:
        return normalize_retention(deck["retention"])
    except (KeyError, IndexError):
        return 0.9


def _due_stamp(now: datetime, outcome) -> str:
    from lexicon.fsrs import due_after

    return _stamp(due_after(now, outcome))


def _item_ids(values) -> list[int]:
    seen = []
    for value in values or []:
        try:
            item_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("choose a saved word") from exc
        if item_id not in seen:
            seen.append(item_id)
    return seen


def _name(value: str) -> str:
    title = " ".join((value or "").split())
    if not title:
        raise ValueError("name the deck")
    if len(title) > 120:
        raise ValueError("that name is too long")
    return title


def _now(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
