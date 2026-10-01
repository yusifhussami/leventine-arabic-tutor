"""Read lesson clusters out of the loaded vocabulary.

A lesson is every row whose Date Added falls on the same calendar day.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Literal

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_date_added(value: str) -> datetime:
    """Parse a Notion timestamp such as '13 September 2026 13:15'.

    Month names are matched in English on purpose. strptime would follow the
    machine locale and reject this export on a non-English system.
    """
    parts = value.split()
    if len(parts) != 4:
        raise ValueError(f"unrecognized Date Added: {value!r}")
    day_text, month_text, year_text, time_text = parts
    try:
        hour_text, minute_text = time_text.split(":")
        return datetime(
            int(year_text),
            _MONTHS[month_text.casefold()],
            int(day_text),
            int(hour_text),
            int(minute_text),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unrecognized Date Added: {value!r}") from exc


def latest_lesson(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return the rows added on the newest day, earliest time first.

    Rows are returned as stored. A blank row or a repeated spelling stays in
    the result. classify_entry labels a row; it does not remove one.
    """
    rows = conn.execute(
        """
        SELECT id, source_row, word, category, date_added, imperative, meaning, status
        FROM entries
        """
    ).fetchall()
    if not rows:
        return []

    dated = [(parse_date_added(row["date_added"]), row) for row in rows]
    newest = max(added.date() for added, _ in dated)
    on_day = [(added, row) for added, row in dated if added.date() == newest]
    on_day.sort(key=lambda item: (item[0], item[1]["source_row"]))
    return [row for _, row in on_day]


EntryKind = Literal["blank", "reversed", "grammar", "phrase", "word"]

# Chat-alphabet digits. A 2 or a 7 inside an English example is not, by itself,
# proof that the columns were swapped.
_ARABIZI_DIGITS = frozenset("2356789")


def classify_entry(row: sqlite3.Row) -> EntryKind:
    """Label one stored row for practice.

    blank is both fields empty. reversed is an English word sitting in the
    word column while the whole meaning is one Arabizi token. grammar, phrase,
    and word are not decided yet, so any other filled row still raises.
    """
    word = (row["word"] or "").strip()
    meaning = (row["meaning"] or "").strip()
    if word == "" and meaning == "":
        return "blank"
    if _is_reversed(word, meaning):
        return "reversed"
    raise NotImplementedError("grammar, phrase, and word are not classified yet")


def _is_reversed(word: str, meaning: str) -> bool:
    """True when the English gloss and the Arabizi spelling traded columns.

    The meaning has to be one token. An English gloss that quotes Arabizi
    later, as in fakker's "ma 2deret afakker", still belongs to a real word.
    """
    return _is_plain_english(word) and _is_arabizi_token(meaning)


def _is_plain_english(text: str) -> bool:
    return bool(text) and all(ch.isascii() and (ch.isalpha() or ch.isspace()) for ch in text)


def _is_arabizi_token(text: str) -> bool:
    if not text or any(ch.isspace() for ch in text):
        return False
    return any(ch in _ARABIZI_DIGITS for ch in text)

