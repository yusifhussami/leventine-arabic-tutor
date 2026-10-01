"""Turn the newest lesson into items you can practice.

A card is a word or a phrase you use in a sentence. A note is grammar from
that same day. Reversed columns are swapped once, then labeled again, so
"joking" / "maze7" is practiced as maze7, "joking".
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from lexicon.lessons import EntryKind, classify_entry, latest_lesson
from lexicon.load import connect, load_entries


@dataclass(frozen=True)
class PracticeCard:
    source_row: int
    kind: EntryKind
    word: str
    meaning: str


@dataclass(frozen=True)
class GrammarNote:
    source_row: int
    word: str
    meaning: str


@dataclass(frozen=True)
class PracticeSession:
    cards: tuple[PracticeCard, ...]
    notes: tuple[GrammarNote, ...]


def practice_session(conn: sqlite3.Connection) -> PracticeSession:
    """Cards and grammar notes from the newest lesson day, in lesson order."""
    cards: list[PracticeCard] = []
    notes: list[GrammarNote] = []
    for row in latest_lesson(conn):
        item = _oriented(row)
        if item is None:
            continue
        kind, word, meaning = item
        if kind in ("word", "phrase"):
            cards.append(
                PracticeCard(row["source_row"], kind, word, meaning)
            )
        elif kind == "grammar":
            notes.append(GrammarNote(row["source_row"], word, meaning))
    return PracticeSession(tuple(cards), tuple(notes))


def _oriented(row: sqlite3.Row) -> tuple[EntryKind, str, str] | None:
    """Return the label and the fields as they should be practiced.

    A blank row and a headword with no gloss are not practice items.
    """
    try:
        kind = classify_entry(row)
    except NotImplementedError:
        return None
    word = (row["word"] or "").strip()
    meaning = (row["meaning"] or "").strip()
    if kind == "blank":
        return None
    if kind != "reversed":
        return kind, word, meaning

    swapped = {key: row[key] for key in row.keys()}
    swapped["word"], swapped["meaning"] = meaning, word
    try:
        kind = classify_entry(swapped)
    except NotImplementedError:
        return None
    if kind not in ("word", "phrase", "grammar"):
        return None
    return kind, meaning, word


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Print practice cards and grammar notes from the newest lesson."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    args = parser.parse_args(argv)

    conn = connect(args.db_path)
    try:
        load_entries(conn, args.csv_path)
        session = practice_session(conn)
    finally:
        conn.close()

    for card in session.cards:
        print(f"{card.kind}: {card.word} — {card.meaning}")
    for note in session.notes:
        label = note.word or "(no headword)"
        print(f"grammar: {label} — {note.meaning}")


if __name__ == "__main__":
    main()
