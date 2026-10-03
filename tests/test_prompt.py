import tempfile
import unittest
from pathlib import Path

from lexicon.load import connect, load_entries
from lexicon.practice import PracticeCard, practice_session
from lexicon.prompt import build_prompt

from tests.test_practice import CSV


class PromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        csv_path = root / "vocab.csv"
        csv_path.write_text(CSV, encoding="utf-8")
        self.conn = connect(root / "lexicon.db")
        load_entries(self.conn, csv_path)
        self.session = practice_session(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_prompt_contains_the_target_sentence_and_same_day_context(self) -> None:
        card = self.session.cards[0]
        prompt = build_prompt(self.session, card, " ra7t 3al ijazeh ")
        self.assertEqual(
            prompt,
            "\n".join(
                [
                    "You are a Levantine Arabic tutor using Arabizi.",
                    "The learner is practicing one target from their latest lesson.",
                    "Judge whether their sentence uses the target in a way that fits the meaning.",
                    "Use the other lesson items and grammar notes only as context.",
                    "Do not invent a sentence for them.",
                    "Write the comment in English. Do not rewrite the learner's Arabizi.",
                    "",
                    "Target (word): ijazeh",
                    "Meaning: holiday",
                    "",
                    "Learner's sentence:",
                    "ra7t 3al ijazeh",
                    "",
                    "Other items from this lesson:",
                    "- maze7: joking",
                    "- met3ale2een feni: relatable to me",
                    "",
                    "Grammar from this lesson:",
                    "- fe3el 2amr: Imperative deed  /verb",
                    "",
                ]
            ),
        )

    def test_japanese_account_uses_romaji_in_the_prompt(self) -> None:
        card = self.session.cards[0]
        prompt = build_prompt(self.session, card, "raht al ijazeh", language="ja")
        self.assertIn("You are a Levantine Arabic tutor using romaji.", prompt)
        self.assertIn(
            "Write the comment in Japanese. Do not rewrite the learner's romaji.",
            prompt,
        )
        self.assertIn("Target (word): ijazeh", prompt)
        self.assertIn("raht al ijazeh", prompt)

    def test_card_from_outside_the_session_is_rejected(self) -> None:
        stranger = PracticeCard(1, "word", "bas", "but")
        with self.assertRaises(ValueError):
            build_prompt(self.session, stranger, "bas hek")


if __name__ == "__main__":
    unittest.main()
