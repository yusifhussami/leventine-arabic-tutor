"""Read lesson clusters out of the loaded vocabulary.

A lesson is every row whose Date Added falls on the same calendar day.
"""

from __future__ import annotations

import re
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
_JAPANESE_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")


def classify_entry(row: sqlite3.Row) -> EntryKind:
    """Label one stored row for practice.

    blank is both fields empty. reversed is English in the word column and one
    Arabizi token as the meaning. grammar is a lesson label, not a word whose
    gloss happens to name a tense. A phrase has a space you would say. A slash
    alternative or a parenthetical paradigm stays one word. A headword with no
    gloss is still unlabeled.
    """
    word = (row["word"] or "").strip()
    meaning = (row["meaning"] or "").strip()
    if word == "" and meaning == "":
        return "blank"
    if _is_reversed(word, meaning):
        return "reversed"
    if _is_grammar(word, meaning):
        return "grammar"
    if meaning == "":
        raise NotImplementedError("a headword with no gloss is not classified yet")
    if _is_phrase(word):
        return "phrase"
    return "word"


def _is_reversed(word: str, meaning: str) -> bool:
    """True when the English gloss and the target spelling traded columns.

    The meaning has to be one token. An English gloss that quotes Arabizi
    later, as in fakker's "ma 2deret afakker", still belongs to a real word.
    Japanese sheets reverse when English is in Word and kana/kanji is Meaning.
    """
    if not _is_plain_english(word):
        return False
    return _is_arabizi_token(meaning) or _is_japanese_token(meaning)


def _is_plain_english(text: str) -> bool:
    return bool(text) and all(ch.isascii() and (ch.isalpha() or ch.isspace()) for ch in text)


def _is_arabizi_token(text: str) -> bool:
    if not text or any(ch.isspace() for ch in text):
        return False
    return any(ch in _ARABIZI_DIGITS for ch in text)


def _is_japanese_token(text: str) -> bool:
    if not text:
        return False
    return bool(_JAPANESE_SCRIPT.search(text))


# These rows name a grammatical idea. A verb glossed "break (imperative)" is
# not here: that is a word you say, with the form noted in parentheses.
# "2amr" / "Order" and "fe3el" / "verb / deed" stay out. Each is also an
# ordinary word, and a keyword rule cannot tell the two uses apart.
_GRAMMAR_NOTES = {
    ("fe3el 2amr", "imperative deed/verb"),
    ("fe3el mustamer", "continuous word"),
    ("jamme3", "plural"),
    ("22mor", "order (imperative)"),
    ("wa9if", "description/adjective"),
    ("ma", "negation (with exception)"),
}


def _is_grammar(word: str, meaning: str) -> bool:
    """True for a rule fragment, or for a headword on the note list.

    A meaning with no headword has nothing to put in a sentence. "mustamer"
    glossed only as "continuous" is not on the list: that row is the adjective.
    """
    if word == "" and meaning != "":
        return True
    return (_normalize_label(word), _normalize_label(meaning)) in _GRAMMAR_NOTES


def _normalize_label(text: str) -> str:
    text = " ".join(text.casefold().split())
    return text.replace(" /", "/").replace("/ ", "/")


def _is_phrase(word: str) -> bool:
    """True when the spelled utterance itself contains more than one word.

    Text inside parentheses is a note about the headword, such as a paradigm.
    Spaces that only separate slash alternatives, as in "5abar / a5bar", are
    two forms of one entry.
    """
    uttered = _without_parentheticals(word).strip()
    collapsed = uttered.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    return any(ch.isspace() for ch in collapsed)


def _without_parentheticals(text: str) -> str:
    kept: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif depth == 0:
            kept.append(char)
    return "".join(kept)

