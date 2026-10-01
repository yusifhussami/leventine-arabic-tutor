import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from lexicon.drill import read_sentence, run_drill
from lexicon.load import connect, load_entries
from lexicon.practice import practice_session

from tests.test_judge import _payload, _Response
from tests.test_practice import CSV


class DrillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        csv_path = root / "vocab.csv"
        csv_path.write_text(CSV, encoding="utf-8")
        self.conn = connect(root / "lexicon.db")
        load_entries(self.conn, csv_path)
        self.session = practice_session(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _opener(self, request, timeout):
        return _Response(_payload(True, True, "ok"))

    def test_blank_skips_and_quit_stops(self) -> None:
        answers = iter(["", "ra7t 3al maze7", "q"])
        output: list[str] = []
        judged = run_drill(
            self.conn,
            self.session,
            "test-key",
            lambda: next(answers),
            output.append,
            self._opener,
        )
        self.assertEqual(judged, 1)
        stored = self.conn.execute("SELECT sentence FROM attempts").fetchall()
        self.assertEqual([row["sentence"] for row in stored], ["ra7t 3al maze7"])
        self.assertEqual(output.count("ok"), 1)
        self.assertIn("Grammar from this lesson:", output)
        self.assertIn("judged 1", output)

    def test_a_prior_sentence_is_shown_before_the_next_attempt(self) -> None:
        card = self.session.cards[0]
        cursor = self.conn.execute(
            """
            INSERT INTO attempts (source_row, word, meaning, sentence, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (card.source_row, card.word, card.meaning, "ra7t 3al ijazeh", "t"),
        )
        self.conn.execute(
            """
            INSERT INTO judgments (
                attempt_id, model, uses_target, fits_meaning, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cursor.lastrowid, "gemini-3.5-flash-lite", 1, 0, "too broad", "t"),
        )
        self.conn.commit()
        output: list[str] = []
        judged = run_drill(
            self.conn,
            self.session,
            "test-key",
            lambda: "q",
            output.append,
        )
        self.assertEqual(judged, 0)
        self.assertIn(
            "  already tried: ra7t 3al ijazeh (uses the target; does not fit the meaning)",
            output,
        )

    def test_closed_input_ends_the_session(self) -> None:
        with patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(read_sentence())


if __name__ == "__main__":
    unittest.main()
