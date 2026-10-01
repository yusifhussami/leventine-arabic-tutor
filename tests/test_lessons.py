import tempfile
import unittest
from pathlib import Path

from lexicon.lessons import latest_lesson, parse_date_added
from lexicon.load import connect, load_entries

from tests.test_load import CSV


class LessonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.csv_path = root / "vocab.csv"
        self.csv_path.write_text(CSV, encoding="utf-8")
        self.conn = connect(root / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_latest_lesson_is_the_newest_day_in_time_order(self) -> None:
        load_entries(self.conn, self.csv_path)
        rows = latest_lesson(self.conn)
        self.assertEqual([row["source_row"] for row in rows], [6, 4])
        self.assertEqual(rows[0]["word"], "")
        self.assertEqual(rows[1]["word"], "6alab")
        self.assertEqual(rows[1]["meaning"], "demand")

    def test_empty_lexicon_has_no_lesson(self) -> None:
        self.assertEqual(latest_lesson(self.conn), [])

    def test_unrecognized_date_is_rejected(self) -> None:
        load_entries(self.conn, self.csv_path)
        self.conn.execute(
            "UPDATE entries SET date_added = ? WHERE source_row = 1",
            ("not a date",),
        )
        with self.assertRaises(ValueError):
            latest_lesson(self.conn)
        with self.assertRaises(ValueError):
            parse_date_added("13 Sep 2026 13:15")


if __name__ == "__main__":
    unittest.main()
