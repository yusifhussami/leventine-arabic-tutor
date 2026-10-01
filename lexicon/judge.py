"""Ask the tutor model whether a sentence uses the practice card, and store the reply.

The call goes through OpenRouter to google/gemini-3.5-flash-lite. The lesson
gloss is the standard, so the model must not look the word up.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lexicon.load import connect, load_entries
from lexicon.practice import PracticeCard, PracticeSession, practice_session, record_attempt
from lexicon.prompt import build_prompt

MODEL = "google/gemini-3.5-flash-lite"
# One sentence a human types is slower than this. The gap only applies when calls bunch up.
_MIN_INTERVAL_SECONDS = 4.0
_MAX_ATTEMPTS = 4
_RETRYABLE = {408, 429, 500, 502, 503, 504}
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_KEY_NAMES = ("OPENROUTER_API_KEY", "GEMINI_API_KEY")

_SCHEMA = {
    "type": "object",
    "properties": {
        "uses_target": {"type": "boolean"},
        "fits_meaning": {"type": "boolean"},
        "comment": {"type": "string"},
    },
    "required": ["uses_target", "fits_meaning", "comment"],
}


@dataclass(frozen=True)
class Judgment:
    id: int
    attempt_id: int
    model: str
    uses_target: bool
    fits_meaning: bool
    comment: str
    created_at: str


@dataclass(frozen=True)
class CardMemory:
    sentence: str
    uses_target: bool | None
    fits_meaning: bool | None
    comment: str | None


def card_history(conn: sqlite3.Connection, card: PracticeCard) -> list[CardMemory]:
    """Earlier sentences for this card, oldest first, with the latest judgment."""
    rows = conn.execute(
        """
        SELECT a.sentence, j.uses_target, j.fits_meaning, j.comment
        FROM attempts a
        LEFT JOIN judgments j ON j.id = (
            SELECT id FROM judgments
            WHERE attempt_id = a.id
            ORDER BY id DESC
            LIMIT 1
        )
        WHERE a.source_row = ? AND a.word = ? AND a.meaning = ?
        ORDER BY a.id
        """,
        (card.source_row, card.word, card.meaning),
    ).fetchall()
    memories: list[CardMemory] = []
    for row in rows:
        judged = row["uses_target"] is not None
        memories.append(
            CardMemory(
                row["sentence"],
                bool(row["uses_target"]) if judged else None,
                bool(row["fits_meaning"]) if judged else None,
                row["comment"],
            )
        )
    return memories


def read_api_key(env_path: Path | str = ".env") -> str:
    """Return the OpenRouter key from the environment, or from a local .env file.

    GEMINI_API_KEY is accepted because that is the name already in .env.
    """
    for name in _KEY_NAMES:
        from_env = os.environ.get(name, "").strip()
        if from_env:
            return from_env
    path = Path(env_path)
    found: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            name, value = text.split("=", 1)
            key = value.strip().strip('"').strip("'")
            if key:
                found[name.strip()] = key
    for name in _KEY_NAMES:
        if name in found:
            return found[name]
    raise RuntimeError("Set OPENROUTER_API_KEY in .env")


def request_body(prompt: str) -> dict:
    """One user turn, a JSON judgment, and the cheapest reasoning level."""
    return {
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "judgment", "strict": True, "schema": _SCHEMA},
        },
        "reasoning": {"effort": "minimal"},
    }


def parse_judgment(payload: dict) -> tuple[bool, bool, str]:
    """Read uses_target, fits_meaning, and comment from a chat completion."""
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("model returned no choices")
    content = choices[0].get("message", {}).get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    data = json.loads(content)
    return bool(data["uses_target"]), bool(data["fits_meaning"]), str(data["comment"])


class RateLimiter:
    """Keep a gap between calls so a burst stays under the minute cap."""

    def __init__(self, min_interval: float = _MIN_INTERVAL_SECONDS, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._clock()
        self._next = now + self.min_interval


_PACE = RateLimiter()


def call_model(
    prompt: str,
    api_key: str,
    opener=urllib.request.urlopen,
    pace: RateLimiter | None = None,
    sleep=time.sleep,
) -> tuple[bool, bool, str]:
    """POST the prompt. The key is sent as a header, not in the URL.

    Calls are spaced, and a rate-limit or outage response is retried. A bad
    request is not retried.
    """
    (pace or _PACE).wait()
    delay = 1.0
    for attempt in range(_MAX_ATTEMPTS):
        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(request_body(prompt)).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
            return parse_judgment(payload)
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE or attempt == _MAX_ATTEMPTS - 1:
                detail = exc.read().decode(errors="replace")[:500]
                raise RuntimeError(f"OpenRouter request failed ({exc.code}): {detail}") from exc
            sleep(_retry_delay(exc, delay))
            delay = min(delay * 2, 8.0)


def _retry_delay(exc: urllib.error.HTTPError, fallback: float) -> float:
    header = exc.headers.get("Retry-After") if exc.headers is not None else None
    if header:
        try:
            return float(header)
        except ValueError:
            return fallback
    return fallback


def judge(
    conn: sqlite3.Connection,
    session: PracticeSession,
    card: PracticeCard,
    sentence: str,
    api_key: str,
    opener=urllib.request.urlopen,
) -> Judgment:
    """Store the sentence, ask the model, and store the structured reply."""
    attempt = record_attempt(conn, card, sentence)
    uses_target, fits_meaning, comment = call_model(
        build_prompt(session, card, sentence),
        api_key,
        opener,
    )
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO judgments (
            attempt_id, model, uses_target, fits_meaning, comment, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            attempt.id,
            MODEL,
            int(uses_target),
            int(fits_meaning),
            comment,
            created_at,
        ),
    )
    conn.commit()
    return Judgment(
        int(cursor.lastrowid),
        attempt.id,
        MODEL,
        uses_target,
        fits_meaning,
        comment,
        created_at,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Judge one sentence against a lesson card.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("word")
    parser.add_argument("sentence")
    args = parser.parse_args(argv)

    conn = connect(args.db_path)
    try:
        load_entries(conn, args.csv_path)
        session = practice_session(conn)
        matches = [card for card in session.cards if card.word == args.word]
        if len(matches) != 1:
            names = ", ".join(card.word for card in session.cards)
            raise SystemExit(f"expected one card named {args.word!r}; cards: {names}")
        result = judge(conn, session, matches[0], args.sentence, read_api_key())
    finally:
        conn.close()

    used = "uses the target" if result.uses_target else "does not use the target"
    fit = "fits the meaning" if result.fits_meaning else "does not fit the meaning"
    print(f"{used}; {fit}")
    print(result.comment)


if __name__ == "__main__":
    main()
