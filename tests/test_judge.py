import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.judge import call_model, judge, parse_judgment, read_api_key, request_body
from lexicon.load import connect, load_entries
from lexicon.practice import practice_session

from tests.test_practice import CSV


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _payload(uses: bool, fits: bool, comment: str) -> dict:
    text = json.dumps(
        {"uses_target": uses, "fits_meaning": fits, "comment": comment}
    )
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "checking the digits"},
                        {"text": text},
                    ]
                }
            }
        ]
    }


class JudgeTests(unittest.TestCase):
    def test_request_stays_a_closed_judgment(self) -> None:
        body = request_body("prompt")
        config = body["generationConfig"]
        self.assertEqual(config["temperature"], 0)
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "minimal"})
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertNotIn("tools", body)

    def test_thought_part_is_ignored(self) -> None:
        uses, fits, comment = parse_judgment(_payload(True, False, "wrong person"))
        self.assertEqual((uses, fits, comment), (True, False, "wrong person"))

    def test_missing_key_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# GEMINI_API_KEY=\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                read_api_key(path)

    def test_judge_stores_the_reply_for_the_attempt(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "vocab.csv"
            csv_path.write_text(CSV, encoding="utf-8")
            conn = connect(root / "lexicon.db")
            try:
                load_entries(conn, csv_path)
                session = practice_session(conn)
                card = session.cards[0]

                def opener(request, timeout):
                    self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
                    self.assertNotIn("key=", request.full_url)
                    return _Response(_payload(True, True, "holiday is used"))

                result = judge(conn, session, card, "ra7t 3al ijazeh", "test-key", opener)
                self.assertTrue(result.uses_target)
                self.assertTrue(result.fits_meaning)
                row = conn.execute(
                    "SELECT attempt_id, model, comment FROM judgments"
                ).fetchone()
                self.assertEqual(row["attempt_id"], result.attempt_id)
                self.assertEqual(row["model"], "gemini-3.5-flash-lite")
                self.assertEqual(row["comment"], "holiday is used")
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        """
                        INSERT INTO judgments (
                            attempt_id, model, uses_target, fits_meaning, comment, created_at
                        ) VALUES (9999, 'm', 1, 1, 'no', 't')
                        """
                    )
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
