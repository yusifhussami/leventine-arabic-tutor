import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.intake import parse_lesson_text
from lexicon.judge import RateLimiter
from lexicon.load import connect, flag_duplicates, load_entries
from lexicon.notebook import (
    _TALK_PACE,
    import_csv,
    import_sheet,
    list_items,
    save_lesson,
    search_items,
    similar_items,
    talk,
    update_item,
)
from lexicon.prefs import save_language

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

    def test_arabic_and_japanese_words_stay_on_separate_notebooks(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-01",
            "baza5 = fancy",
            embed=_vectors,
            language="arabic",
        )
        save_lesson(
            self.conn,
            "2026-10-02",
            "hello - konnichiwa",
            embed=lambda glosses: [[1.0, 0.0] for _ in glosses],
            language="japanese",
        )
        arabic = list_items(self.conn, language="arabic")
        japanese = list_items(self.conn, language="japanese")
        self.assertEqual([item["spelling"] for item in arabic], ["baza5"])
        self.assertEqual([item["spelling"] for item in japanese], ["konnichiwa"])
        save_language(self.conn, "japanese")
        self.assertEqual(
            [item["spelling"] for item in list_items(self.conn)],
            ["konnichiwa"],
        )
        save_language(self.conn, "arabic")
        self.assertEqual(
            [item["spelling"] for item in list_items(self.conn)],
            ["baza5"],
        )

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
        self.assertLess(_TALK_PACE.min_interval, 1.0)
        with self.assertRaises(ValueError):
            talk(self.conn, [], "test-key", opener, pace=RateLimiter(min_interval=0))

    def test_talk_only_sees_words_for_the_active_language(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-01",
            "baza5 = fancy",
            embed=_vectors,
            language="arabic",
        )
        save_lesson(
            self.conn,
            "2026-10-02",
            "hello - konnichiwa",
            embed=lambda glosses: [[0.0, 1.0] for _ in glosses],
            language="japanese",
        )

        def opener(request, timeout):
            prompt = json.loads(request.data.decode())["messages"][0]["content"]
            self.assertIn("konnichiwa = hello", prompt)
            self.assertNotIn("baza5", prompt)
            return _TalkResponse(
                {
                    "you_arabizi": "konnichiwa",
                    "you_english": "hello",
                    "arabic": "こんにちは",
                    "arabizi": "konnichiwa",
                    "english": "hello",
                    "correction": "",
                    "better": "",
                }
            )

        talk(
            self.conn,
            [{"role": "user", "text": "こんにちは"}],
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
            language="japanese",
        )

    def test_talk_japanese_learning_uses_romaji_and_japanese_speech(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-01",
            "hello - konnichiwa\ncoffee - koohii",
            embed=lambda glosses: [[1.0, 0.0] for _ in glosses],
            language="japanese",
        )

        def opener(request, timeout):
            body = json.loads(request.data.decode())
            prompt = body["messages"][0]["content"]
            self.assertIn("LANGUAGE LOCK: japanese", prompt)
            self.assertIn("You are a Japanese friend", prompt)
            self.assertIn("This call is entirely in Japanese", prompt)
            self.assertIn("Speak natural Japanese", prompt)
            self.assertIn("konnichiwa = hello", prompt)
            self.assertNotIn("2 is ء or أ", prompt)
            return _TalkResponse(
                {
                    "you_arabizi": "konnichiwa",
                    "you_english": "hello",
                    "arabic": "こんにちは",
                    "arabizi": "konnichiwa",
                    "english": "hello",
                    "correction": "",
                    "better": "",
                }
            )

        reply = talk(
            self.conn,
            [{"role": "user", "text": "こんにちは"}],
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
            language="japanese",
        )
        self.assertEqual(reply["you_arabizi"], "konnichiwa")
        self.assertEqual(reply["arabizi"], "konnichiwa")
        self.assertEqual(reply["arabic"], "こんにちは")
        self.assertEqual(reply["english"], "hello")
        self.assertEqual(reply["language"], "japanese")

    def test_talk_japanese_retries_when_model_answers_in_arabizi(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-01",
            "thanks - arigatou",
            embed=lambda glosses: [[1.0, 0.0] for _ in glosses],
            language="japanese",
        )
        calls = {"n": 0}

        def opener(request, timeout):
            calls["n"] += 1
            prompt = json.loads(request.data.decode())["messages"][0]["content"]
            if calls["n"] == 1:
                return _TalkResponse(
                    {
                        "you_arabizi": "arigatou",
                        "you_english": "thanks",
                        "arabic": "أهلا فيك",
                        "arabizi": "ahlan feek! keefak?",
                        "english": "welcome how are you",
                        "correction": "",
                        "better": "",
                    }
                )
            self.assertIn("IMPORTANT CORRECTION", prompt)
            self.assertIn("wrong language", prompt)
            return _TalkResponse(
                {
                    "you_arabizi": "arigatou",
                    "you_english": "thanks",
                    "arabic": "どういたしまして",
                    "arabizi": "douitashimashite",
                    "english": "you're welcome",
                    "correction": "",
                    "better": "",
                }
            )

        reply = talk(
            self.conn,
            [{"role": "user", "text": "ありがとう"}],
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
            language="japanese",
        )
        self.assertEqual(calls["n"], 2)
        self.assertEqual(reply["arabizi"], "douitashimashite")
        self.assertEqual(reply["arabic"], "どういたしまして")

    def test_talk_japanese_coffee_scene_uses_japanese_romaji(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-01",
            "please - kudasai\ncoffee - koohii",
            embed=lambda glosses: [[1.0, 0.0] for _ in glosses],
            language="japanese",
        )

        def opener(request, timeout):
            prompt = json.loads(request.data.decode())["messages"][0]["content"]
            self.assertIn("koohii", prompt)
            self.assertIn("kudasai", prompt)
            self.assertNotIn("7elo", prompt)
            return _TalkResponse(
                {
                    "you_arabizi": "",
                    "you_english": "",
                    "arabic": "いらっしゃいませ",
                    "arabizi": "irasshaimase",
                    "english": "welcome",
                    "correction": "",
                    "better": "",
                }
            )

        reply = talk(
            self.conn,
            [{"role": "user", "text": "Start. You speak first."}],
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
            language="japanese",
            scene="coffee",
        )
        self.assertEqual(reply["arabizi"], "irasshaimase")
        self.assertEqual(reply["arabic"], "いらっしゃいませ")

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

    def test_csv_upload_fills_an_empty_notebook(self) -> None:
        def embed(texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0] for _ in texts]

        csv_text = (
            "Word,Meaning,Date Added\n"
            "keefak,how are you,18 June 2026 15:15\n"
            "joking,maze7,18 June 2026 15:16\n"
            "jamme3,plural,18 June 2026 15:17\n"
            "bas,but,\n"
        )
        first = import_csv(self.conn, csv_text, embed=embed, default_day="2026-10-03")
        self.assertEqual(first["items"], 3)
        self.assertEqual(first["days"], 2)
        spellings = {item["spelling"] for item in list_items(self.conn)}
        self.assertEqual(spellings, {"keefak", "maze7", "bas"})
        by_day = {item["spelling"]: item["learned_on"] for item in list_items(self.conn)}
        self.assertEqual(by_day["keefak"], "2026-06-18")
        self.assertEqual(by_day["bas"], "2026-10-03")
        with self.assertRaisesRegex(ValueError, "no new words"):
            import_csv(self.conn, csv_text, embed=embed, default_day="2026-10-03")

    def test_japanese_csv_import_stores_kana_with_kanji_on_the_gloss(self) -> None:
        def embed(texts: list[str]) -> list[list[float]]:
            return [[0.0, 1.0] for _ in texts]

        csv_text = (
            "Kanji,Kana,Meaning\n"
            "今日は,こんにちは,hello\n"
            "水,みず,water\n"
        )
        saved = import_csv(
            self.conn,
            csv_text,
            embed=embed,
            default_day="2026-10-03",
            language="japanese",
        )
        self.assertEqual(saved["items"], 2)
        items = {
            item["spelling"]: item["gloss"]
            for item in list_items(self.conn, language="japanese")
        }
        self.assertEqual(
            items,
            {
                "こんにちは": "hello · 今日は",
                "みず": "water · 水",
            },
        )
        self.assertEqual(list_items(self.conn, language="arabic"), [])


if __name__ == "__main__":
    unittest.main()
