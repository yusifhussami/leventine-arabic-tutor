"""Practice the newest lesson one card at a time.

A blank line skips a card. q stops. Each sentence is judged and stored.
"""

from __future__ import annotations

import argparse
import urllib.request
from typing import Callable, Optional
from pathlib import Path

from lexicon.judge import judge, read_api_key
from lexicon.load import connect, load_entries
from lexicon.practice import PracticeSession, practice_session

LineReader = Callable[[], Optional[str]]
Writer = Callable[[str], None]


def run_drill(
    conn,
    session: PracticeSession,
    api_key: str,
    read_line: LineReader,
    write: Writer,
    opener=urllib.request.urlopen,
) -> int:
    """Show each card, read a sentence, and print the judgment.

    Returns how many sentences were judged. Tests pass opener so the model
    call stays off the network.
    """
    if session.notes:
        write("Grammar from this lesson:")
        for note in session.notes:
            label = note.word or "(no headword)"
            write(f"  {label} — {note.meaning}")

    judged = 0
    total = len(session.cards)
    for index, card in enumerate(session.cards, start=1):
        write(f"{index}/{total} {card.kind}: {card.word} — {card.meaning}")
        line = read_line()
        if line is None:
            break
        text = line.strip()
        if text.casefold() in {"q", "quit"}:
            break
        if not text:
            continue
        result = judge(conn, session, card, text, api_key, opener)
        judged += 1
        used = "uses the target" if result.uses_target else "does not use the target"
        fit = "fits the meaning" if result.fits_meaning else "does not fit the meaning"
        write(f"{used}; {fit}")
        write(result.comment)
    write(f"judged {judged}")
    return judged


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Practice the newest lesson. An empty line skips a card. q stops."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    args = parser.parse_args(argv)

    conn = connect(args.db_path)
    try:
        load_entries(conn, args.csv_path)
        session = practice_session(conn)
        if not session.cards:
            raise SystemExit("the newest lesson has no words or phrases to practice")
        run_drill(conn, session, read_api_key(), input, print)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
