import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.intake import parse_lesson_text
from lexicon.load import connect
from lexicon.notebook import list_items, save_lesson, similar_items

SAMPLE = (
    "baza5 = fancy we7deh = loneliness "
    "7ayat al baza5 fiha we7deh = rich life has loneliness"
)


def _vectors(glosses: list[str]) -> list[list[float]]:
    table = {
        "fancy": [1.0, 0.0],
        "loneliness": [0.0, 1.0],
        "rich life has loneliness": [0.8, 0.6],
    }
    return [table[gloss] for gloss in glosses]


class IntakeTests(unittest.TestCase):
    def test_chain_separates_each_spelling_from_its_gloss(self) -> None:
        pairs = parse_lesson_text(SAMPLE)
        self.assertEqual(
            pairs,
            [
                ("baza5", "fancy"),
                ("we7deh", "loneliness"),
                ("7ayat al baza5 fiha we7deh", "rich life has loneliness"),
            ],
        )

    def test_one_pair_per_line(self) -> None:
        pairs = parse_lesson_text("bas = but\namma = as for / but\n")
        self.assertEqual(pairs, [("bas", "but"), ("amma", "as for / but")])


class NotebookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_a_lesson_keeps_every_pair_and_ranks_similar_glosses(self) -> None:
        saved = save_lesson(self.conn, "2026-10-01", SAMPLE, embed=_vectors)
        self.assertEqual(
            [(item["spelling"], item["kind"]) for item in saved["items"]],
            [
                ("baza5", "word"),
                ("we7deh", "word"),
                ("7ayat al baza5 fiha we7deh", "phrase"),
            ],
        )
        self.assertEqual(len(list_items(self.conn)), 3)
        baza5 = saved["items"][0]["id"]
        nearest = similar_items(self.conn, baza5)
        self.assertEqual(nearest[0]["spelling"], "7ayat al baza5 fiha we7deh")
        self.assertGreater(nearest[0]["score"], 0.5)


if __name__ == "__main__":
    unittest.main()
