import sqlite3
import tempfile
import unittest
from pathlib import Path

from lexicon.load import connect, flag_duplicates, load_entries, parse_vocabulary_csv


CSV = """\
Word,Category,Date Added,Imperative,Meaning,Status
bas,Core and Connectors,18 June 2026 15:15,No,but,Unmarked
bas ,Core and Connectors,2 July 2026 15:04,No,But,Unmarked
6alab,Abstract and Topics,18 June 2026 15:17,No,request,Unmarked
6alab,Core and Connectors,13 September 2026 12:50,No,demand,Unmarked
, ,12 July 2026 12:47,No,,
, ,13 September 2026 12:48,No,,
"""


class LoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.csv_path = root / "vocab.csv"
        self.csv_path.write_text(CSV, encoding="utf-8")
        self.conn = connect(root / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_load_keeps_every_row_and_replaces_on_second_run(self) -> None:
        self.assertEqual(load_entries(self.conn, self.csv_path), 6)
        self.assertEqual(load_entries(self.conn, self.csv_path), 6)
        count = self.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        self.assertEqual(count, 6)
        word = self.conn.execute(
            "SELECT word FROM entries WHERE source_row = 2"
        ).fetchone()["word"]
        self.assertEqual(word, "bas ")

    def test_flag_splits_exact_copies_from_different_glosses(self) -> None:
        load_entries(self.conn, self.csv_path)
        flags = flag_duplicates(self.conn)
        self.assertEqual(flags, {"groups": 2, "exact_copy": 1, "same_spelling": 1})

        kinds = {
            row["normalized_word"]: row["kind"]
            for row in self.conn.execute("SELECT normalized_word, kind FROM duplicate_groups")
        }
        self.assertEqual(kinds, {"bas": "exact_copy", "6alab": "same_spelling"})
        blank_groups = self.conn.execute(
            "SELECT COUNT(*) FROM duplicate_groups WHERE normalized_word = ''"
        ).fetchone()[0]
        self.assertEqual(blank_groups, 0)

    def test_foreign_key_rejects_a_member_with_no_entry(self) -> None:
        load_entries(self.conn, self.csv_path)
        flag_duplicates(self.conn)
        group_id = self.conn.execute("SELECT id FROM duplicate_groups LIMIT 1").fetchone()["id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO duplicate_members (group_id, entry_id) VALUES (?, ?)",
                (group_id, 9999),
            )

    def test_parse_accepts_simple_word_meaning_csv(self) -> None:
        rows = parse_vocabulary_csv("Arabizi,English\nkeefak,how are you\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["word"], "keefak")
        self.assertEqual(rows[0]["meaning"], "how are you")
        self.assertEqual(rows[0]["date_added"], "")

    def test_parse_japanese_csv_prefers_kana_and_keeps_kanji(self) -> None:
        rows = parse_vocabulary_csv(
            "Kanji,Hiragana,English\n"
            "今日は,こんにちは,hello\n"
            "水,みず,water\n"
            ",ありがとう,thank you\n"
        )
        self.assertEqual(
            [(row["word"], row["meaning"]) for row in rows],
            [
                ("こんにちは", "hello · 今日は"),
                ("みず", "water · 水"),
                ("ありがとう", "thank you"),
            ],
        )

    def test_parse_rejects_csv_without_meaning_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "spelling and meaning columns"):
            parse_vocabulary_csv("Word,Status\nbas,Unmarked\n")


if __name__ == "__main__":
    unittest.main()
