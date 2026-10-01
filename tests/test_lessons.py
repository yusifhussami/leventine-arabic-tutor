import tempfile
import unittest
from pathlib import Path

from lexicon.lessons import classify_entry, latest_lesson, parse_date_added
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

    def test_blank_row_is_blank(self) -> None:
        load_entries(self.conn, self.csv_path)
        blank = latest_lesson(self.conn)[0]
        self.assertEqual(classify_entry(blank), "blank")

    def test_filled_row_is_not_classified_yet(self) -> None:
        load_entries(self.conn, self.csv_path)
        filled = latest_lesson(self.conn)[1]
        with self.assertRaises(NotImplementedError):
            classify_entry(filled)

    def test_swapped_columns_are_reversed(self) -> None:
        path = Path(self.tmp.name) / "swapped.csv"
        path.write_text(
            "Word,Category,Date Added,Imperative,Meaning,Status\n"
            "to expect,,13 September 2026 12:52,No,etwa8a3,\n"
            "joking,,13 September 2026 12:58,No,maze7,\n"
            "England,,12 July 2026 13:03,No,Bri6ania,\n"
            'fakker,Verbs,18 June 2026 15:15,No,"to think; e.g. ma 2deret afakker",\n'
            "ijazeh,,13 September 2026 12:39,No,holiday,\n",
            encoding="utf-8",
        )
        load_entries(self.conn, path)
        rows = {
            row["word"]: row
            for row in self.conn.execute("SELECT word, meaning FROM entries")
        }
        self.assertEqual(classify_entry(rows["to expect"]), "reversed")
        self.assertEqual(classify_entry(rows["joking"]), "reversed")
        self.assertEqual(classify_entry(rows["England"]), "reversed")
        with self.assertRaises(NotImplementedError):
            classify_entry(rows["fakker"])
        with self.assertRaises(NotImplementedError):
            classify_entry(rows["ijazeh"])

    def test_grammar_notes_are_not_the_words_they_describe(self) -> None:
        path = Path(self.tmp.name) / "grammar.csv"
        path.write_text(
            "Word,Category,Date Added,Imperative,Meaning,Status\n"
            "fe3el 2amr ,,18 June 2026 15:15,No,Imperative deed  /verb ,\n"
            "jamme3 ,,12 July 2026 13:09,No,plural,\n"
            "ma,,12 July 2026 13:06,No,negation (with exception),\n"
            ",,12 July 2026 13:07,No,when negating people,\n"
            "ekser,Verbs,18 June 2026 15:15,No,break (mild, imperative),\n"
            "mustamer,Descriptors,18 June 2026 15:15,No,continuous,\n"
            "2amr,Verbs,18 June 2026 15:15,No,Order,\n"
            "fe3el,Goals and Ideas,18 June 2026 15:15,No,verb / deed,\n",
            encoding="utf-8",
        )
        load_entries(self.conn, path)
        rows = list(self.conn.execute("SELECT word, meaning FROM entries ORDER BY source_row"))
        self.assertEqual(
            [classify_entry(row) for row in rows[:4]],
            ["grammar", "grammar", "grammar", "grammar"],
        )
        for row in rows[4:]:
            with self.assertRaises(NotImplementedError):
                classify_entry(row)


if __name__ == "__main__":
    unittest.main()
