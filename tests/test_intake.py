import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.intake import parse_lesson_text
from lexicon.judge import RateLimiter
from lexicon.load import connect, flag_duplicates, load_entries
from lexicon.notebook import (
    import_sheet,
    list_items,
    save_lesson,
    search_items,
    similar_items,
    talk,
    update_item,
)

SAMPLE = (
    "baza5 = fancy we7deh = loneliness "
    "7ayat al baza5 fiha we7deh = rich life has loneliness"
)


class _TalkResponse:
    def __init__(self, data: dict) -> None:
        self._payload = json.dumps(
            {"choices": [{"message": {"content": json.dumps(data)}}]}
        ).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_TalkResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


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

    def test_english_dash_arabizi_and_equals_split_each_word(self) -> None:
        pairs = parse_lesson_text(
            "practice - tadreeb to train - etdarrab 8ararat = decisions"
        )
        self.assertEqual(
            pairs,
            [
                ("tadreeb", "practice"),
                ("etdarrab", "to train"),
                ("8ararat", "decisions"),
            ],
        )


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

    def test_editing_a_word_replaces_its_spelling_gloss_and_vector(self) -> None:
        saved = save_lesson(self.conn, "2026-10-01", SAMPLE, embed=_vectors)
        item_id = saved["items"][0]["id"]

        def embed(glosses: list[str]) -> list[list[float]]:
            self.assertEqual(glosses, ["luxurious"])
            return [[0.0, 1.0]]

        updated = update_item(self.conn, item_id, "  hayet baza5  ", "luxurious", embed=embed)
        self.assertEqual(updated["spelling"], "hayet baza5")
        self.assertEqual(updated["gloss"], "luxurious")
        self.assertEqual(updated["kind"], "phrase")
        stored = next(item for item in list_items(self.conn) if item["id"] == item_id)
        self.assertEqual((stored["spelling"], stored["gloss"]), ("hayet baza5", "luxurious"))
        self.assertEqual(similar_items(self.conn, item_id)[0]["spelling"], "we7deh")

        def unused(glosses: list[str]) -> list[list[float]]:
            raise AssertionError(glosses)

        same = update_item(self.conn, item_id, "baza5", "luxurious", embed=unused)
        self.assertEqual(same["kind"], "word")
        with self.assertRaises(ValueError):
            update_item(self.conn, item_id, " ", "fancy", embed=unused)
        with self.assertRaises(LookupError):
            update_item(self.conn, 999, "bas", "but", embed=unused)

    def test_saving_the_same_word_again_does_not_keep_a_copy(self) -> None:
        save_lesson(self.conn, "2026-10-01", SAMPLE, embed=_vectors)
        with self.assertRaises(ValueError):
            save_lesson(self.conn, "2026-10-02", SAMPLE, embed=_vectors)
        self.assertEqual(len(list_items(self.conn)), 3)
        saved = save_lesson(self.conn, "2026-10-02", "baza5 = fancy\nbas = but", embed=lambda glosses: [[0.0, 0.0]])
        self.assertEqual([item["spelling"] for item in saved["items"]], ["bas"])
        self.assertEqual([item["spelling"] for item in saved["skipped"]], ["baza5"])
        self.assertEqual(len(list_items(self.conn)), 4)

    def test_talk_replies_from_saved_words(self) -> None:
        save_lesson(self.conn, "2026-10-01", SAMPLE, embed=_vectors)

        def opener(request, timeout):
            body = json.loads(request.data.decode())
            self.assertIn("baza5 = fancy", body["messages"][0]["content"])
            self.assertIn("keefak", body["messages"][0]["content"])
            self.assertEqual(body["max_tokens"], 280)
            return _TalkResponse(
                {
                    "you_arabizi": "mar7aba",
                    "you_english": "hello",
                    "arabic": "كيفك",
                    "arabizi": "kifak",
                    "english": "how's it going",
                    "correction": "",
                    "better": "",
                }
            )

        reply = talk(
            self.conn,
            [{"role": "user", "text": "hi"}],
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
        )
        self.assertEqual(reply["arabizi"], "kifak")
        with self.assertRaises(ValueError):
            talk(self.conn, [], "test-key", opener, pace=RateLimiter(min_interval=0))

    def test_sheet_import_is_searchable_by_spelling_and_meaning(self) -> None:
        csv_path = Path(self.tmp.name) / "vocab.csv"
        csv_path.write_text(
            "Word,Category,Date Added,Imperative,Meaning,Status\n"
            "bas,Core,18 June 2026 15:15,No,but,\n"
            "bas,Core,2 July 2026 15:04,No,But,\n"
            "jamme3,,12 July 2026 13:09,No,plural,\n"
            "joking,,13 September 2026 12:58,No,maze7,\n"
            "we7deh,,13 September 2026 13:00,No,loneliness,\n",
            encoding="utf-8",
        )
        load_entries(self.conn, csv_path)
        flag_duplicates(self.conn)

        def embed(texts: list[str]) -> list[list[float]]:
            table = {"but": [1.0, 0.0], "joking": [1.0, 0.0], "loneliness": [0.2, 0.9], "lonely": [0.1, 1.0]}
            return [table.get(text, [0.0, 0.0]) for text in texts]

        first = import_sheet(self.conn, embed=embed)
        second = import_sheet(self.conn, embed=embed)
        self.assertEqual(second, {"days": 0, "items": 0})
        self.assertEqual(first["items"], 3)
        spellings = {item["spelling"] for item in list_items(self.conn) if item["learned_on"] != "2026-10-01"}
        self.assertEqual(spellings, {"bas", "maze7", "we7deh"})
        self.assertEqual(search_items(self.conn, "we7", embed=embed)[0]["spelling"], "we7deh")
        lonely = search_items(self.conn, "lonely", embed=embed)
        self.assertEqual(lonely[0]["spelling"], "we7deh")
        self.assertEqual(lonely[0]["match"], "meaning")


if __name__ == "__main__":
    unittest.main()
