import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.arabic_script import (
    SOURCE_AI,
    SOURCE_DICTIONARY,
    SOURCE_USER,
    PageSource,
    apply_arabic,
    backfill,
    clean_arabic,
    dictionary_arabic,
    fill_arabic_items,
    gloss_heads,
    resolve_rows,
    transliterate_arabizi,
)
from lexicon.db import ARABIC_ITEM_ALTERS
from lexicon.judge import RateLimiter
from lexicon.load import connect, migrate_notebook_schema
from lexicon.notebook import export_words_csv, import_csv, list_items, save_lesson, update_item, words_csv


def _embed(texts):
    return [[0.0, 0.0] for _ in texts]


def _quiet_pace():
    return RateLimiter(min_interval=0, clock=lambda: 0.0, sleep=lambda _seconds: None)


BUT = """
* Arabic: {{t+|ar|لٰكِن}}, {{t+|ar|لٰكِنَّ}}
*: Egyptian Arabic: {{t|arz|بس|tr=bas}}
*: South Levantine Arabic: {{t|ajp|لكن|tr=lāken}}, {{t|ajp|بسّ|tr=bass}}
"""

TOMORROW = """
* Arabic: {{t+|ar|غَدًا}}
*: North Levantine Arabic: {{tt|apc|بكرة|tr=bukra}}
*: South Levantine Arabic: {{tt|ajp|بكرة|tr=bukra}}
"""

NORMAL = "* Arabic: {{t|ar|عَادِيّ}}\n"
HOWAREYOU = "*: North Levantine Arabic: {{t|apc|كِيفَك؟|m|tr=kīfak?}}\n*: Mesopotamian Arabic: {{t|apc|شْلُونَك؟|tr=šlōnak?}}\n"
TALK = "* Arabic: {{t+|ar|تَكَلَّمَ}}, {{t|ar|تَحَدَّثَ}}\n"
SWEAT = "* Arabic: {{tt+|ar|عَرَق|m}}\n*: Egyptian Arabic: {{tt|arz|عرق|m|tr=ʕaraʔ}}\n"
COFFEE = "*: Egyptian Arabic: {{tt|arz|قَهْوَة|f|tr=ʔahwa}}\n* Arabic: {{tt+|ar|قَهْوَة|f}}\n"

PAGES = {
    "but": "",
    "but/translations": BUT,
    "tomorrow": "",
    "tomorrow/translations": TOMORROW,
    "normal": NORMAL,
    "normal/translations": "",
    "how are you": "",
    "how are you/translations": HOWAREYOU,
    "how": "",
    "how/translations": "",
    "talk": TALK,
    "talk/translations": "",
    "sweat": SWEAT,
    "sweat/translations": "",
    "coffee": "",
    "coffee/translations": COFFEE,
}


def _fetch(title: str) -> str:
    return PAGES.get(title.casefold(), "")


class LookupTests(unittest.TestCase):
    def test_gloss_heads_prefer_the_phrase_then_one_content_word(self) -> None:
        self.assertEqual(gloss_heads("but"), ["but"])
        self.assertEqual(gloss_heads("to search"), ["search"])
        self.assertEqual(gloss_heads("how are you"), ["how are you", "how"])
        self.assertEqual(gloss_heads("normal / fine / usually (habit)"), ["normal", "fine"])

    def test_dictionary_picks_the_levantine_line_that_matches_the_arabizi(self) -> None:
        self.assertEqual(dictionary_arabic("bas", "but", _fetch), "بسّ")
        self.assertEqual(dictionary_arabic("bokra", "tomorrow", _fetch), "بكرة")
        self.assertEqual(dictionary_arabic("keefak", "how are you", _fetch), "كِيفَك")
        self.assertEqual(dictionary_arabic("3adi", "normal", _fetch), "عَادِيّ")
        self.assertEqual(dictionary_arabic("ahwe", "coffee", _fetch), "قَهْوَة")

    def test_inner_hamza_does_not_let_a_short_word_match_a_longer_one(self) -> None:
        page = "* Arabic: {{t+|ar|هٰؤُلَاءِ}}\n"

        def fetch(title: str) -> str:
            return page if title.casefold() == "this" else ""

        self.assertIsNone(dictionary_arabic("hal", "this", fetch))

    def test_dictionary_misses_when_the_arabizi_does_not_match(self) -> None:
        self.assertIsNone(dictionary_arabic("b-y-a7ko", "they talk", _fetch))
        self.assertIsNone(dictionary_arabic("3are9'", "sweat", _fetch))
        self.assertNotIn("livingarabic", " ".join(PAGES))

    def test_transliteration_is_arabic_letters_and_not_stored_unchecked(self) -> None:
        guess = transliterate_arabizi("bas")
        self.assertEqual(guess, "بس")
        self.assertTrue(clean_arabic("عرق (sweat)") == "عرق")


class FallbackTests(unittest.TestCase):
    def test_model_fills_a_dictionary_miss_and_a_repeat_uses_the_cache(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conn = connect(Path(tmp.name) / "lexicon.db")
        self.addCleanup(conn.close)
        saved = save_lesson(conn, "2026-04-02", "b-y-a7ko = they talk", embed=_embed)
        item_id = saved["items"][0]["id"]
        calls = {"http": 0, "model": 0}

        def opener(request, timeout=30):
            calls["http"] += 1
            self.assertIn("en.wiktionary.org/w/api.php", request.full_url)
            self.assertNotIn("livingarabic", request.full_url)
            self.assertIn("Sawt/1.0", request.get_header("User-agent"))
            payload = {"query": {"pages": {"1": {"title": "Talk", "missing": ""}}}}

            class Response:
                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Response()

        def complete(body, api_key, pace=None, **kwargs):
            calls["model"] += 1
            self.assertEqual(api_key, "test-key")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"items": [{"id": str(item_id), "arabic": "بيحكوا"}]}
                            )
                        }
                    }
                ]
            }

        rows = [{"id": item_id, "spelling": "b-y-a7ko", "gloss": "they talk"}]
        first = resolve_rows(
            conn,
            rows,
            opener=opener,
            complete_fn=complete,
            api_key="test-key",
            pace=_quiet_pace(),
        )
        self.assertEqual(first, [{"id": item_id, "arabic": "بيحكوا", "source": SOURCE_AI}])
        self.assertGreaterEqual(calls["http"], 1)
        http_after_first = calls["http"]
        second = resolve_rows(
            conn,
            rows,
            opener=opener,
            complete_fn=complete,
            api_key="test-key",
            pace=_quiet_pace(),
        )
        self.assertEqual(second[0]["source"], SOURCE_AI)
        self.assertEqual(calls["model"], 1)
        self.assertEqual(calls["http"], http_after_first)


class MigrationTests(unittest.TestCase):
    def test_old_sqlite_notebook_gains_empty_arabic_columns(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "old.db"
        raw = sqlite3.connect(path)
        raw.execute(
            """
            CREATE TABLE lessons (
                id INTEGER PRIMARY KEY,
                learned_on TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        raw.execute(
            """
            CREATE TABLE lesson_items (
                id INTEGER PRIMARY KEY,
                lesson_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                spelling TEXT NOT NULL,
                gloss TEXT NOT NULL,
                kind TEXT NOT NULL,
                UNIQUE (lesson_id, position)
            )
            """
        )
        raw.execute(
            "INSERT INTO lessons (id, learned_on, raw_text, created_at) VALUES (1, '2026-01-01', 'bas = but', 't')"
        )
        raw.execute(
            "INSERT INTO lesson_items (id, lesson_id, position, spelling, gloss, kind) VALUES (1, 1, 0, 'bas', 'but', 'word')"
        )
        raw.commit()
        raw.close()

        conn = connect(path)
        self.addCleanup(conn.close)
        row = conn.execute("SELECT spelling, arabic_script, arabic_source FROM lesson_items").fetchone()
        self.assertEqual(row["spelling"], "bas")
        self.assertEqual(row["arabic_script"], "")
        self.assertEqual(row["arabic_source"], "")
        migrate_notebook_schema(conn)
        again = conn.execute("PRAGMA table_info(lesson_items)").fetchall()
        names = [item[1] for item in again]
        self.assertEqual(names.count("arabic_script"), 1)
        self.assertEqual(names.count("arabic_source"), 1)
        cached = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'script_cache'"
        ).fetchone()
        self.assertIsNotNone(cached)

    def test_postgres_alter_is_idempotent(self) -> None:
        sql = "\n".join(ARABIC_ITEM_ALTERS)
        self.assertIn("ADD COLUMN IF NOT EXISTS arabic_script", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS arabic_source", sql)
        self.assertEqual(len(ARABIC_ITEM_ALTERS), 2)


class BackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_backfill_is_idempotent_and_skips_user_edits_and_japanese(self) -> None:
        save_lesson(self.conn, "2026-01-15", "bas = but\n3are9' = sweat", embed=_embed)
        save_lesson(
            self.conn,
            "2026-02-01",
            "mizu = water",
            embed=_embed,
            language="japanese",
        )
        rows = {item["spelling"]: item for item in list_items(self.conn, language="arabic")}
        update_item(
            self.conn,
            rows["3are9'"]["id"],
            "3are9'",
            "sweat",
            embed=_embed,
            arabic_script="عرق",
        )
        seen: list[list[str]] = []

        def resolver(pending):
            seen.append([row["spelling"] for row in pending])
            return [
                {"id": row["id"], "arabic": "بس", "source": SOURCE_DICTIONARY}
                for row in pending
            ]

        first = backfill(self.conn, resolver=resolver, batch=10)
        self.assertEqual(first["filled"], 1)
        self.assertEqual(first["dictionary"], 1)
        self.assertEqual(first["remaining"], 0)
        self.assertEqual(seen, [["bas"]])
        stored = {item["spelling"]: item for item in list_items(self.conn, language="arabic")}
        self.assertEqual(stored["bas"]["arabic_script"], "بس")
        self.assertEqual(stored["bas"]["arabic_source"], SOURCE_DICTIONARY)
        self.assertEqual(stored["3are9'"]["arabic_script"], "عرق")
        self.assertEqual(stored["3are9'"]["arabic_source"], SOURCE_USER)
        japanese = list_items(self.conn, language="japanese")
        self.assertEqual(japanese[0]["arabic_script"], "")
        self.assertEqual(japanese[0]["arabic_source"], "")

        def refuse(pending):
            raise AssertionError(pending)

        second = backfill(self.conn, resolver=refuse, batch=10)
        self.assertEqual(second["filled"], 0)
        self.assertEqual(second["seen"], 0)
        again = {item["spelling"]: item for item in list_items(self.conn, language="arabic")}
        self.assertEqual(again["3are9'"]["arabic_script"], "عرق")
        self.assertEqual(again["bas"]["arabic_source"], SOURCE_DICTIONARY)

    def test_a_miss_stays_open_and_a_hit_is_not_sent_again(self) -> None:
        save_lesson(self.conn, "2026-01-15", "bas = but\nb-y-a7ko = they talk", embed=_embed)
        calls = []

        def resolver(pending):
            calls.append(sorted(row["spelling"] for row in pending))
            found = []
            for row in pending:
                if row["spelling"] == "bas":
                    found.append({"id": row["id"], "arabic": "بس", "source": SOURCE_AI})
            return found

        backfill(self.conn, resolver=resolver, batch=10)
        backfill(self.conn, resolver=resolver, batch=10)
        self.assertEqual(calls[0], ["b-y-a7ko", "bas"])
        self.assertEqual(calls[1], ["b-y-a7ko"])

    def test_same_arabic_text_keeps_the_dictionary_source(self) -> None:
        saved = save_lesson(self.conn, "2026-01-15", "bas = but", embed=_embed)
        item_id = saved["items"][0]["id"]
        self.conn.execute(
            "UPDATE lesson_items SET arabic_script = ?, arabic_source = ? WHERE id = ?",
            ("بس", SOURCE_DICTIONARY, item_id),
        )
        self.conn.commit()
        update_item(self.conn, item_id, "bas", "however", embed=_embed, arabic_script="بس")
        row = list_items(self.conn)[0]
        self.assertEqual(row["gloss"], "however")
        self.assertEqual(row["arabic_source"], SOURCE_DICTIONARY)
        update_item(self.conn, item_id, "bas", "however", embed=_embed, arabic_script="لكن")
        edited = list_items(self.conn)[0]
        self.assertEqual(edited["arabic_script"], "لكن")
        self.assertEqual(edited["arabic_source"], SOURCE_USER)
        apply_arabic(
            self.conn,
            [{"id": item_id, "arabic": "بس", "source": SOURCE_AI}],
        )
        self.assertEqual(list_items(self.conn)[0]["arabic_script"], "لكن")

    def test_imported_arabic_column_is_user_text_and_blocks_backfill(self) -> None:
        text = words_csv(
            [
                {
                    "id": 1,
                    "spelling": "b-y-a7ko",
                    "arabic_script": "بيحكوا",
                    "gloss": "they talk",
                    "kind": "word",
                    "learned_on": "2026-04-02",
                }
            ],
            language="arabic",
        )
        self.assertEqual(
            text.splitlines()[0].lstrip("\ufeff"),
            "Arabizi,Arabic,English,Kind,Date Added,Language",
        )
        saved = import_csv(self.conn, text, embed=_embed, default_day="2026-04-02")
        self.assertEqual(saved["items"], 1)
        row = list_items(self.conn)[0]
        self.assertEqual(row["arabic_script"], "بيحكوا")
        self.assertEqual(row["arabic_source"], SOURCE_USER)
        fill_arabic_items(
            self.conn,
            item_ids=saved["item_ids"],
            resolver=lambda rows: [
                {"id": row["id"], "arabic": "يتحدثون", "source": SOURCE_AI} for row in rows
            ],
        )
        self.assertEqual(list_items(self.conn)[0]["arabic_script"], "بيحكوا")
        filename, exported = export_words_csv(self.conn, language="arabic")
        self.assertTrue(filename.startswith("sawt-words-"))
        self.assertIn("b-y-a7ko,بيحكوا,they talk", exported)

    def test_page_source_does_not_fetch_a_cached_title_again(self) -> None:
        calls = []

        def opener(request, timeout=30):
            calls.append(request.full_url)
            payload = {
                "query": {
                    "pages": {
                        "10": {
                            "title": "But",
                            "revisions": [{"slots": {"main": {"*": BUT}}}],
                        }
                    }
                }
            }

            class Response:
                def read(self):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Response()

        source = PageSource(self.conn, opener=opener, pace=_quiet_pace())
        source.prefetch(["but"])
        source.prefetch(["but"])
        self.assertEqual(len(calls), 1)
        self.assertIn(BUT.strip().splitlines()[0], source("but"))


if __name__ == "__main__":
    unittest.main()
