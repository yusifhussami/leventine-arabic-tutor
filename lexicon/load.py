"""Load a Notion vocabulary export into SQLite and flag repeated spellings.

Each CSV row is stored as-is. Repeated spellings go in a group of their own,
with no canonical winner: an exact re-import and two real glosses of the same
spelling are different kinds of duplicate.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

REQUIRED_COLUMNS = {
    "Word",
    "Category",
    "Date Added",
    "Imperative",
    "Meaning",
    "Status",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    source_row INTEGER NOT NULL,
    word TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    date_added TEXT NOT NULL DEFAULT '',
    imperative TEXT NOT NULL DEFAULT '',
    meaning TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT ''
);

-- A group is one normalized spelling that showed up more than once.
-- kind distinguishes a repeated import from two meanings that share a spelling.
CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY,
    normalized_word TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('exact_copy', 'same_spelling'))
);

-- Member rows point at both parents. CASCADE keeps flags from outliving a reload.
CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups (id) ON DELETE CASCADE,
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_duplicate_members_entry
    ON duplicate_members (entry_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a database and enforce foreign keys on this connection.

    SQLite parses REFERENCES clauses either way, but it only rejects a bad
    member row when this pragma is on. The setting is per connection, so every
    opener has to set it again.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def normalize_word(word: str) -> str:
    """Spelling key: case, surrounding space, and apostrophe shape don't count."""
    text = word.strip().casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return " ".join(text.split())


def normalize_meaning(meaning: str) -> str:
    text = meaning.strip().casefold()
    return " ".join(text.split())


def load_entries(conn: sqlite3.Connection, csv_path: Path | str) -> int:
    """Replace entries with the CSV. Clears duplicate flags, since they point at old ids."""
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"CSV is missing columns: {sorted(missing)}")
        records = [
            (
                source_row,
                row.get("Word") or "",
                (row.get("Category") or "").strip(),
                (row.get("Date Added") or "").strip(),
                (row.get("Imperative") or "").strip(),
                row.get("Meaning") or "",
                (row.get("Status") or "").strip(),
            )
            for source_row, row in enumerate(reader, start=1)
        ]

    with conn:
        conn.execute("DELETE FROM duplicate_members")
        conn.execute("DELETE FROM duplicate_groups")
        conn.execute("DELETE FROM entries")
        conn.executemany(
            """
            INSERT INTO entries (
                source_row, word, category, date_added, imperative, meaning, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
    return len(records)


def flag_duplicates(conn: sqlite3.Connection) -> dict[str, int]:
    """Group spellings that occur more than once. Blank words are not a group."""
    rows = conn.execute("SELECT id, word, meaning FROM entries").fetchall()
    grouped: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        key = normalize_word(row["word"])
        if not key:
            continue
        grouped.setdefault(key, []).append((row["id"], normalize_meaning(row["meaning"])))

    exact_copy = 0
    same_spelling = 0
    with conn:
        conn.execute("DELETE FROM duplicate_members")
        conn.execute("DELETE FROM duplicate_groups")
        for key, members in grouped.items():
            if len(members) < 2:
                continue
            meanings = {meaning for _, meaning in members}
            kind = "exact_copy" if len(meanings) == 1 else "same_spelling"
            cursor = conn.execute(
                """
                INSERT INTO duplicate_groups (normalized_word, kind)
                VALUES (?, ?)
                """,
                (key, kind),
            )
            group_id = cursor.lastrowid
            conn.executemany(
                """
                INSERT INTO duplicate_members (group_id, entry_id)
                VALUES (?, ?)
                """,
                [(group_id, entry_id) for entry_id, _ in members],
            )
            if kind == "exact_copy":
                exact_copy += 1
            else:
                same_spelling += 1

    return {
        "groups": exact_copy + same_spelling,
        "exact_copy": exact_copy,
        "same_spelling": same_spelling,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Load a vocabulary CSV into SQLite and flag duplicate spellings."
    )
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    args = parser.parse_args(argv)

    conn = connect(args.db_path)
    try:
        loaded = load_entries(conn, args.csv_path)
        flags = flag_duplicates(conn)
    finally:
        conn.close()

    print(f"loaded {loaded} entries")
    print(
        f"flagged {flags['groups']} groups "
        f"({flags['exact_copy']} exact copies, {flags['same_spelling']} same spelling)"
    )


if __name__ == "__main__":
    main()
