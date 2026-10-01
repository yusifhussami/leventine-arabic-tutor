import tempfile
import unittest
from pathlib import Path

from lexicon.load import connect, load_entries
from lexicon.practice import attempts_for, practice_session, record_attempt

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

    def test_attempt_is_stored_against_the_card_and_survives_reload(self) -> None:
        card = practice_session(self.conn).cards[0]
        saved = record_attempt(self.conn, card, "  ra7t 3al ijazeh  ")
        self.assertEqual(saved.sentence, "ra7t 3al ijazeh")
        load_entries(self.conn, self.csv_path)
        stored = attempts_for(self.conn, card)
        self.assertEqual(
            [(item.word, item.meaning, item.sentence) for item in stored],
            [("ijazeh", "holiday", "ra7t 3al ijazeh")],
        )

    def test_blank_sentence_is_rejected(self) -> None:
        card = practice_session(self.conn).cards[0]
        with self.assertRaises(ValueError):
            record_attempt(self.conn, card, "   ")
        self.assertEqual(attempts_for(self.conn, card), [])


if __name__ == "__main__":
    unittest.main()
