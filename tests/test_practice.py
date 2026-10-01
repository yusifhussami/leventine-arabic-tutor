import tempfile
import unittest
from pathlib import Path

from lexicon.load import connect, load_entries
from lexicon.practice import practice_session

CSV = """\
Word,Category,Date Added,Imperative,Meaning,Status
bas,Core and Connectors,18 June 2026 15:15,No,but,Unmarked
jamme3,,12 July 2026 13:09,No,plural,
ijazeh ,,13 September 2026 12:39,No,holiday,
,,13 September 2026 12:48,No,,
joking,,13 September 2026 12:58,No,maze7,
met3ale2een feni,,13 September 2026 13:07,No,relatable to me,
Homework,,13 September 2026 13:20,No,,
fe3el 2amr ,,13 September 2026 13:21,No,Imperative deed  /verb ,
"""


class PracticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.csv_path = root / "vocab.csv"
        self.csv_path.write_text(CSV, encoding="utf-8")
        self.conn = connect(root / "lexicon.db")
        load_entries(self.conn, self.csv_path)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_newest_day_becomes_cards_and_notes(self) -> None:
        session = practice_session(self.conn)
        self.assertEqual(
            [(card.kind, card.word, card.meaning) for card in session.cards],
            [
                ("word", "ijazeh", "holiday"),
                ("word", "maze7", "joking"),
                ("phrase", "met3ale2een feni", "relatable to me"),
            ],
        )
        self.assertEqual(
            [(note.word, note.meaning) for note in session.notes],
            [("fe3el 2amr", "Imperative deed  /verb")],
        )


if __name__ == "__main__":
    unittest.main()
