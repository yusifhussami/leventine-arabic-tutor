"""Open the notebook store: Supabase/Postgres when DATABASE_URL is set, else SQLite."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from lexicon.load import connect as connect_sqlite

LOCAL_USER = "local"

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'arabic',
    learned_on TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_items (
    id BIGSERIAL PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    spelling TEXT NOT NULL,
    gloss TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('word', 'phrase')),
    UNIQUE (lesson_id, position)
);

CREATE TABLE IF NOT EXISTS lesson_embeddings (
    item_id BIGINT PRIMARY KEY REFERENCES lesson_items (id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    vector TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_attempts (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES lesson_items (id) ON DELETE CASCADE,
    sentence TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_judgments (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES lesson_attempts (id) ON DELETE CASCADE,
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


class PgConnection:
    """psycopg connection that accepts SQLite-style ? placeholders."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.backend = "postgres"

    def execute(self, sql: str, params=()):
        return self._conn.execute(_pg_sql(sql), params)

    def executemany(self, sql: str, seq_of_params) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(_pg_sql(sql), seq_of_params)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


def _pg_sql(sql: str) -> str:
    text = sql.replace("?", "%s")
    text = text.replace("ON CONFLICT(item_id)", "ON CONFLICT (item_id)")
    text = text.replace("ON CONFLICT(user_id, key)", "ON CONFLICT (user_id, key)")
    return text


def database_url() -> str:
    return (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()


def open_db(db_path: Path | str = "lexicon.db", *, sqlite_only: bool = False):
    """Supabase/Postgres when DATABASE_URL is set, otherwise the local SQLite file.

    Pass sqlite_only=True for `python3 -m lexicon.serve` so a DATABASE_URL in
    .env does not hijack the local notebook file.
    """
    url = "" if sqlite_only else database_url()
    if url:
        return open_postgres(url)
    conn = connect_sqlite(db_path)
    try:
        conn.backend = "sqlite"  # type: ignore[attr-defined]
    except AttributeError:
        # Some Python builds use a slotted Connection; tag via wrapper attr unused.
        pass
    return conn


def open_postgres(url: str) -> PgConnection:
    import psycopg
    from psycopg.rows import dict_row

    # Supabase transaction pooler (port 6543) does not support prepared statements.
    conn = psycopg.connect(
        _postgres_connect_url(url),
        row_factory=dict_row,
        autocommit=False,
        prepare_threshold=None,
    )
    wrapped = PgConnection(conn)
    try:
        for statement in PG_SCHEMA.split(";"):
            text = statement.strip()
            if text:
                wrapped.execute(text)
        # Existing hosted DBs were created before language existed.
        wrapped.execute(
            "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'arabic'"
        )
        wrapped.execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_user "
            "ON lessons (user_id, learned_on DESC, id DESC)"
        )
        wrapped.execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_user_lang "
            "ON lessons (user_id, language, learned_on DESC, id DESC)"
        )
        wrapped.commit()
    except Exception:
        wrapped.close()
        raise
    return wrapped


def _postgres_connect_url(url: str) -> str:
    """Normalize hosted Postgres URLs (SSL). Leave DNS alone so the pooler can use IPv4."""
    return _supabase_url(url)


def _supabase_url(url: str) -> str:
    """Ensure SSL for hosted Postgres URLs that omit sslmode."""
    if "sslmode=" in url or "localhost" in url or "127.0.0.1" in url:
        return url
    join = "&" if "?" in url else "?"
    return url + join + "sslmode=require"


def insert_id(conn, sql: str, params) -> int:
    """Run an INSERT and return the new integer id."""
    if getattr(conn, "backend", "sqlite") == "postgres":
        row = conn.execute(sql + " RETURNING id", params).fetchone()
        return int(row["id"])
    cursor = conn.execute(sql, params)
    return int(cursor.lastrowid)
