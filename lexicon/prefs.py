"""Language the learner is studying: Levantine Arabic or Japanese.

The app UI stays English. Mic, TTS, talk prompts, and Latin spelling follow
the learning language.
"""

from __future__ import annotations

from lexicon.db import LOCAL_USER

LANGUAGES = frozenset({"arabic", "japanese"})
DEFAULT_LANGUAGE = "arabic"
_ALIASES = {
    "en": "arabic",
    "ja": "japanese",
    "arabizi": "arabic",
    "romaji": "japanese",
    "levantine": "arabic",
}


def normalize_language(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    cleaned = _ALIASES.get(cleaned, cleaned)
    return cleaned if cleaned in LANGUAGES else DEFAULT_LANGUAGE


def get_language(conn, user_id: str = LOCAL_USER) -> str:
    """Language being learned: arabic or japanese."""
    row = conn.execute(
        "SELECT value FROM settings WHERE user_id = ? AND key = 'language'",
        (user_id,),
    ).fetchone()
    return normalize_language(row["value"] if row else DEFAULT_LANGUAGE)


def save_language(conn, language: str, user_id: str = LOCAL_USER) -> str:
    raw = (language or "").strip().lower()
    if not raw or (raw not in LANGUAGES and raw not in _ALIASES):
        raise ValueError("language must be arabic or japanese")
    cleaned = normalize_language(raw)
    with conn:
        conn.execute(
            "INSERT INTO settings (user_id, key, value) VALUES (?, 'language', ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, cleaned),
        )
    return cleaned


def learning_label(language: str) -> str:
    return "Japanese" if normalize_language(language) == "japanese" else "Levantine Arabic"


def writing_system(language: str) -> str:
    """Latin spelling on the page for the learning language."""
    return "romaji" if normalize_language(language) == "japanese" else "arabizi"


def writing_system_label(language: str) -> str:
    return "romaji" if normalize_language(language) == "japanese" else "Arabizi"


def mic_locale(language: str) -> str:
    return "ja-JP" if normalize_language(language) == "japanese" else "ar-SA"


def speech_script_label(language: str) -> str:
    return "Japanese" if normalize_language(language) == "japanese" else "Arabic"
