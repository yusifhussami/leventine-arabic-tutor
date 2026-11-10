import csv
import io
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.http_api import file_response
from lexicon.load import connect, parse_vocabulary_csv
from lexicon.notebook import (
    export_words_csv,
    import_csv,
    list_items,
    save_lesson,
    update_item,
    words_csv,
)


def _embed(texts):
    return [[0.0, 0.0] for _ in texts]


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))


class WordsCsvTests(unittest.TestCase):
    def test_quotes_commas_apostrophes_and_hyphenated_arabizi(self) -> None:
        text = words_csv(
            [
                {
                    "id": 2,
                    "spelling": "b-y-a7ko",
                    "gloss": 'she said "hello", then left',
                    "kind": "word",
                    "learned_on": "2026-04-02",
                },
                {
                    "id": 3,
                    "spelling": "ya reet",
                    "gloss": "I wish",
                    "kind": "phrase",
                    "learned_on": "2026-01-15",
                },
                {
                    "id": 1,
                    "spelling": "3are9'",
                    "gloss": "sweat",
                    "kind": "word",
                    "learned_on": "2026-01-15",
                },
                {
                    "id": 4,
                    "spelling": "مرحبا",
                    "gloss": "hello\nthere",
                    "kind": "word",
                    "learned_on": "2026-01-15",
                },
            ],
            language="arabic",
        )
        raw = text.encode("utf-8")
        self.assertEqual(raw[:3], b"\xef\xbb\xbf")
        self.assertIn("3are9'".encode("utf-8"), raw)
        self.assertIn("b-y-a7ko".encode("utf-8"), raw)
        self.assertIn("مرحبا".encode("utf-8"), raw)
        self.assertIn(b"\r\n", raw)
        self.assertIn(b'"she said ""hello"", then left"', raw)
        # Apostrophes, digits, and hyphens do not need quotes.
        self.assertIn("\r\n3are9',sweat,word,2026-01-15,Levantine Arabic\r\n", text)
        rows = _rows(text)
        self.assertEqual(
            rows[0],
            ["Arabizi", "English", "Kind", "Date Added", "Language"],
        )
        self.assertEqual(
            rows[1:],
            [
                ["3are9'", "sweat", "word", "2026-01-15", "Levantine Arabic"],
                ["ya reet", "I wish", "phrase", "2026-01-15", "Levantine Arabic"],
                ["مرحبا", "hello\nthere", "word", "2026-01-15", "Levantine Arabic"],
                [
                    "b-y-a7ko",
                    'she said "hello", then left',
                    "word",
                    "2026-04-02",
                    "Levantine Arabic",
                ],
            ],
        )
        for row in rows:
            self.assertEqual(len(row), 5)

    def test_parsed_sheet_keeps_the_same_cells(self) -> None:
        text = words_csv(
            [
                {
                    "id": 1,
                    "spelling": "3are9'",
                    "gloss": 'sweat, "a lot"',
                    "kind": "word",
                    "learned_on": "2026-01-15",
                },
                {
                    "id": 2,
                    "spelling": "b-y-a7ko",
                    "gloss": "they talk",
                    "kind": "word",
                    "learned_on": "2026-04-02",
                },
            ],
            language="arabic",
        )
        parsed = {row["word"]: row for row in parse_vocabulary_csv(text)}
        self.assertEqual(parsed["3are9'"]["meaning"], 'sweat, "a lot"')
        self.assertEqual(parsed["3are9'"]["date_added"], "2026-01-15")
        self.assertEqual(parsed["b-y-a7ko"]["meaning"], "they talk")

    def test_japanese_header_is_spelling_and_kanji_stays_on_the_gloss(self) -> None:
        text = words_csv(
            [
                {
                    "id": 1,
                    "spelling": "こんにちは",
                    "gloss": "hello · 今日は",
                    "kind": "word",
                    "learned_on": "2026-05-01",
                }
            ],
            language="japanese",
        )
        rows = _rows(text)
        self.assertEqual(
            rows[0],
            ["Spelling", "English", "Kind", "Date Added", "Language"],
        )
        self.assertEqual(
            rows[1],
            ["こんにちは", "hello · 今日は", "word", "2026-05-01", "Japanese"],
        )
        parsed = parse_vocabulary_csv(text)
        self.assertEqual(parsed[0]["word"], "こんにちは")
        self.assertEqual(parsed[0]["meaning"], "hello · 今日は")

    def test_empty_notebook_is_still_a_header_row(self) -> None:
        rows = _rows(words_csv([], language="arabic"))
        self.assertEqual(
            rows,
            [["Arabizi", "English", "Kind", "Date Added", "Language"]],
        )


class ExportWordsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_export_is_this_user_and_language_only(self) -> None:
        save_lesson(
            self.conn,
            "2026-04-02",
            "b-y-a7ko = they talk",
            embed=_embed,
            user_id="yusif",
        )
        save_lesson(
            self.conn,
            "2026-01-15",
            "3are9' = sweat",
            embed=_embed,
            user_id="yusif",
        )
        save_lesson(
            self.conn,
            "2026-03-01",
            "ahwe = coffee",
            embed=_embed,
            user_id="someone-else",
        )
        save_lesson(
            self.conn,
            "2026-03-01",
            "mizu = water",
            embed=_embed,
            user_id="yusif",
            language="japanese",
        )
        tricky = next(
            item
            for item in list_items(self.conn, user_id="yusif", language="arabic")
            if item["spelling"] == "b-y-a7ko"
        )
        update_item(
            self.conn,
            tricky["id"],
            "b-y-a7ko",
            'she said "hello", then left',
            embed=_embed,
            user_id="yusif",
        )
        filename, text = export_words_csv(
            self.conn,
            user_id="yusif",
            language="arabic",
            exported_on=date(2026, 11, 10),
        )
        self.assertEqual(filename, "sawt-words-2026-11-10.csv")
        rows = _rows(text)
        self.assertEqual(
            [row[0] for row in rows[1:]],
            ["3are9'", "b-y-a7ko"],
        )
        self.assertEqual(rows[2][1], 'she said "hello", then left')
        self.assertNotIn("ahwe", text)
        self.assertNotIn("mizu", text)
        self.assertNotIn("water", text)

        fresh = connect(Path(self.tmp.name) / "again.db")
        try:
            saved = import_csv(
                fresh,
                text,
                embed=_embed,
                user_id="yusif",
                default_day="2026-11-10",
                language="arabic",
            )
            self.assertEqual(saved["items"], 2)
            restored = {
                item["spelling"]: item["gloss"]
                for item in list_items(fresh, user_id="yusif", language="arabic")
            }
            self.assertEqual(
                restored,
                {
                    "3are9'": "sweat",
                    "b-y-a7ko": 'she said "hello", then left',
                },
            )
        finally:
            fresh.close()


class FileResponseTests(unittest.TestCase):
    def test_download_headers_keep_the_filename_on_one_line(self) -> None:
        handler = _FakeHandler()
        body = "\ufeffArabizi,English\r\n".encode("utf-8")
        file_response(handler, body, "text/csv; charset=utf-8", 'sawt-words-2026-11-10.csv\r\n"')
        self.assertEqual(handler.status, 200)
        headers = dict(handler.headers)
        self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(
            headers["Content-Disposition"],
            'attachment; filename="sawt-words-2026-11-10.csv"',
        )
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(handler.body, body)


class _FakeHandler:
    def __init__(self) -> None:
        self.status = None
        self.headers: list[tuple[str, str]] = []
        self.body = b""
        self.wfile = self

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        return None

    def write(self, data: bytes) -> None:
        self.body += data


if __name__ == "__main__":
    unittest.main()
