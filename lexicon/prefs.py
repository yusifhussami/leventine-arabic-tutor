"""Account language: metalanguage + Latin spelling system.

English accounts use Arabizi (digit letters). Japanese accounts use romaji.
Arabic script for TTS and mic language stay Arabic either way.
"""

from __future__ import annotations

from lexicon.db import LOCAL_USER

LANGUAGES = frozenset({"en", "ja"})
DEFAULT_LANGUAGE = "en"


def get_language(conn, user_id: str = LOCAL_USER) -> str:
    """Account language: English (Arabizi) or Japanese (romaji). Never Arabic."""
    row = conn.execute(
        "SELECT value FROM settings WHERE user_id = ? AND key = 'language'",
        (user_id,),
    ).fetchone()
    value = ((row["value"] if row else "") or DEFAULT_LANGUAGE).strip().lower()
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def save_language(conn, language: str, user_id: str = LOCAL_USER) -> str:
    cleaned = (language or "").strip().lower()
    if cleaned not in LANGUAGES:
        raise ValueError("language must be en or ja")
    with conn:
        conn.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (?, 'language', ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, cleaned),
        )
    return cleaned


def metalanguage_label(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


def writing_system(language: str) -> str:
    """Latin spelling system tied to the account language."""
    return "romaji" if language == "ja" else "arabizi"


def writing_system_label(language: str) -> str:
    return "romaji" if language == "ja" else "Arabizi"
