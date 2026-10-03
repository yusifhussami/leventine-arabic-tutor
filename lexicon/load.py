"""Load a Notion vocabulary export into SQLite and flag repeated spellings.

Each CSV row is stored as-is. Repeated spellings go in a group of their own,
with no canonical winner: an exact re-import and two real glosses of the same
spelling are different kinds of duplicate.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
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

_WORD_HEADERS = frozenset({"word", "arabizi", "romaji", "spelling", "latin"})
_MEANING_HEADERS = frozenset(
    {"meaning", "english", "gloss", "japanese", "日本語", "translation"}
)
_DATE_HEADERS = frozenset({"date added", "date", "learned on", "learned_on", "day"})

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

-- Attempts outlive a CSV reload. entries.id is assigned again on every load,
-- so a foreign key to entries would delete the learner's sentences.
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    source_row INTEGER NOT NULL,
    word TEXT NOT NULL,
    meaning TEXT NOT NULL,
    sentence TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_card
    ON attempts (source_row, word, meaning);

-- A judgment is the model reply for one stored sentence. attempt ids stay put
-- across a CSV reload, so this foreign key is safe.
CREATE TABLE IF NOT EXISTS judgments (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES attempts (id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    uses_target INTEGER NOT NULL CHECK (uses_target IN (0, 1)),
    fits_meaning INTEGER NOT NULL CHECK (fits_meaning IN (0, 1)),
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- A dated batch of words the learner types after a lesson.
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    language TEXT NOT NULL DEFAULT 'arabic',
    learned_on TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Indexes that need user_id/language are created in migrate_notebook_schema
-- after older local databases get those columns.

CREATE TABLE IF NOT EXISTS lesson_items (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    spelling TEXT NOT NULL,
    gloss TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('word', 'phrase')),
    UNIQUE (lesson_id, position)
);

-- The vector is the English gloss, so "fancy" can meet "rich".
CREATE TABLE IF NOT EXISTS lesson_embeddings (
    item_id INTEGER PRIMARY KEY REFERENCES lesson_items (id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    vector TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_attempts (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES lesson_items (id) ON DELETE CASCADE,
    sentence TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_judgments (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES lesson_attempts (id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    uses_target INTEGER NOT NULL CHECK (uses_target IN (0, 1)),
    fits_meaning INTEGER NOT NULL CHECK (fits_meaning IN (0, 1)),
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
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
    # Create missing tables first. Migrate older local DBs before any index that
    # needs user_id / language — CREATE INDEX would otherwise fail on old files.
    conn.executescript(SCHEMA)
    migrate_notebook_schema(conn)
    path = Path(db_path)
    if path.exists():
        os.chmod(path, 0o600)
    return conn


def migrate_notebook_schema(conn: sqlite3.Connection) -> None:
    """Add user_id / language columns for older local databases."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "lessons" in tables:
        lesson_cols = {row[1] for row in conn.execute("PRAGMA table_info(lessons)")}
        if "user_id" not in lesson_cols:
            conn.execute(
                "ALTER TABLE lessons ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'"
            )
        lesson_cols = {row[1] for row in conn.execute("PRAGMA table_info(lessons)")}
        if "language" not in lesson_cols:
            conn.execute(
                "ALTER TABLE lessons ADD COLUMN language TEXT NOT NULL DEFAULT 'arabic'"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_user_lang "
            "ON lessons (user_id, language, learned_on DESC, id DESC)"
        )
    if "settings" in tables:
        setting_cols = {row[1] for row in conn.execute("PRAGMA table_info(settings)")}
        if setting_cols and "user_id" not in setting_cols:
            conn.executescript(
                """
                CREATE TABLE settings_v2 (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (user_id, key)
                );
                INSERT INTO settings_v2 (user_id, key, value)
                SELECT 'local', key, value FROM settings;
                DROP TABLE settings;
                ALTER TABLE settings_v2 RENAME TO settings;
                """
            )
    conn.commit()


def normalize_word(word: str) -> str:
    """Spelling key: case, surrounding space, and apostrophe shape don't count."""
    text = word.strip().casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return " ".join(text.split())


def normalize_meaning(meaning: str) -> str:
    text = meaning.strip().casefold()
    return " ".join(text.split())


def _header_map(fieldnames: list[str] | None) -> dict[str, str]:
    """Map logical fields to the CSV header names that are present."""
    found: dict[str, str] = {}
    for name in fieldnames or []:
        key = " ".join((name or "").strip().casefold().split())
        if key in _WORD_HEADERS and "word" not in found:
            found["word"] = name
        elif key in _MEANING_HEADERS and "meaning" not in found:
            found["meaning"] = name
        elif key in _DATE_HEADERS and "date" not in found:
            found["date"] = name
        elif key == "category" and "category" not in found:
            found["category"] = name
        elif key == "imperative" and "imperative" not in found:
            found["imperative"] = name
        elif key == "status" and "status" not in found:
            found["status"] = name
    return found


def parse_vocabulary_csv(text: str) -> list[dict]:
    """Read a vocabulary CSV from text into row dicts for notebook import.

    Needs a spelling column (Word / Arabizi / Romaji / Spelling) and a meaning
    column (Meaning / English / Gloss). Date Added is optional. Extra Notion
    columns are kept when present.
    """
    if text is None or not str(text).strip():
        raise ValueError("CSV is empty")
    handle = io.StringIO(str(text).lstrip("\ufeff"))
    reader = csv.DictReader(handle)
    columns = _header_map(reader.fieldnames)
    if "word" not in columns or "meaning" not in columns:
        raise ValueError(
            "CSV needs a Word column and a Meaning column "
            "(Arabizi/Romaji/Spelling and English/Gloss also work)"
        )
    rows: list[dict] = []
    for source_row, row in enumerate(reader, start=1):
        rows.append(
            {
                "source_row": source_row,
                "word": row.get(columns["word"]) or "",
                "meaning": row.get(columns["meaning"]) or "",
                "date_added": (row.get(columns["date"]) or "").strip()
                if "date" in columns
                else "",
                "category": (row.get(columns["category"]) or "").strip()
                if "category" in columns
                else "",
                "imperative": (row.get(columns["imperative"]) or "").strip()
                if "imperative" in columns
                else "",
                "status": (row.get(columns["status"]) or "").strip()
                if "status" in columns
                else "",
            }
        )
    if not rows:
        raise ValueError("CSV has no data rows")
    return rows


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
        # attempts stay. They snapshot the card, and entries.id changes on reload.
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
