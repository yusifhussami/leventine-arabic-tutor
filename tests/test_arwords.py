import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from lexicon.arwords import FormsParser, IndexParser, match, match_csv, match_notebook
from lexicon.arabic_script import fill_arabic_items, resolve_rows
from lexicon.load import connect
from lexicon.notebook import list_items, save_lesson


ENTRIES = {"coffee": [{"arabic": "قهوة", "meaning": "coffee", "url": "https://www.arwords.com/words/view/1"}]}


class ArwordsTests(unittest.TestCase):
    def test_index_extracts_entries_and_next_without_following_previous(self):
        parser = IndexParser()
        parser.feed('<table><tr><td><a href="/words/view/1"><span>قهوة</span></a></td><td>coffee &amp; tea</td></tr><tr><td><a href="/words/index/1">Previous</a></td><td><a href="/words/index/3">Next</a></td></tr></table>')
        self.assertEqual(parser.rows[0]["arabic"], "قهوة")
        self.assertEqual(parser.rows[0]["meaning"], "coffee & tea")
        self.assertEqual(parser.next_url, "https://www.arwords.com/words/index/3")

    def test_matching_requires_both_meaning_and_arabizi(self):
        self.assertEqual(match("ahwe", "coffee", entries=ENTRIES), "قهوة")
        self.assertIsNone(match("madrase", "coffee", entries=ENTRIES))
        self.assertIsNone(match("ahwe", "school", entries=ENTRIES))

    def test_ambiguous_spellings_are_left_for_review(self):
        entries = {"write": [{"arabic": "كتب"}, {"arabic": "كاتب"}]}
        self.assertIsNone(match("katab", "write", entries=entries))

    def test_diacritic_variants_do_not_make_one_spelling_ambiguous(self):
        entries = {"but": [{"arabic": "بس"}, {"arabic": "بسّ"}]}
        self.assertEqual(match("bas", "but", entries=entries), "بس")

    def test_forms_prevent_matching_an_inflection_to_the_wrong_lemma(self):
        entries = {"be": [{"arabic": "كان", "forms": [{"arabic": "كان", "translit": "kaan", "dialect": "Leb."}]}]}
        self.assertIsNone(match("koon", "be", entries=entries))
        self.assertEqual(match("kaan", "be", entries=entries), "كان")

    def test_chat_spelling_may_omit_short_vowels(self):
        entries = {"but": [{"arabic": "بس", "forms": [{"arabic": "بَسّ", "translit": "bs", "dialect": "Leb."}]}]}
        self.assertEqual(match("bas", "but", entries=entries), "بَسّ")

    def test_forms_parser_keeps_the_arabic_and_chat_spelling_together(self):
        parser = FormsParser()
        parser.feed('<table><tr><td><span class="ar_word_form">قهوة</span><br><span class="chat_view">2ahwi</span></td><td>noun</td><td class="form_dialect">Leb.</td></tr></table>')
        self.assertEqual(parser.forms, [{"arabic": "قهوة", "translit": "2ahwi", "dialect": "Leb."}])

    def test_known_arwords_match_needs_no_network_and_retains_its_source(self):
        def refuse_network(*args, **kwargs):
            raise AssertionError("A bundled match must not use the network")
        with patch("lexicon.arwords.dictionary", return_value=ENTRIES):
            result = resolve_rows(None, [{"id": 1, "spelling": "ahwe", "gloss": "coffee"}], opener=refuse_network)
        self.assertEqual(result, [{"id": 1, "arabic": "قهوة", "source": "arwords"}])

    def test_automatic_fill_accepts_arwords_source(self):
        with TemporaryDirectory() as directory:
            conn = connect(Path(directory) / "test.db")
            save_lesson(conn, "2026-11-16", "ahwe = coffee", embed=lambda texts: [None] * len(texts))
            with patch("lexicon.arwords.dictionary", return_value=ENTRIES):
                result = fill_arabic_items(conn, user_id="local")
            self.assertEqual(result["arwords"], 1)
            self.assertEqual(list_items(conn)[0]["arabic_source"], "arwords")
            conn.close()

    def test_matching_is_account_scoped_and_keeps_manual_edits(self):
        with TemporaryDirectory() as directory:
            conn = connect(Path(directory) / "test.db")
            for user in ("local", "other"):
                save_lesson(conn, "2026-11-16", "ahwe = coffee", user_id=user, embed=lambda texts: [None] * len(texts))
            with patch("lexicon.arwords.dictionary", return_value=ENTRIES):
                self.assertEqual(match_notebook(conn, "local")["matched"], 1)
                self.assertEqual(match_notebook(conn, "local")["matched"], 0)
                self.assertEqual(list_items(conn, user_id="other")[0]["arabic_script"], "")
                conn.execute("UPDATE lesson_items SET arabic_script = 'قهوتي', arabic_source = 'user' WHERE id = ?", (list_items(conn)[0]["id"],))
                conn.commit()
                self.assertEqual(match_notebook(conn, "local")["matched"], 0)
                self.assertEqual(list_items(conn)[0]["arabic_script"], "قهوتي")
            conn.close()

    def test_csv_preserves_rows_and_marks_unmatched_words(self):
        with TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.csv", Path(directory) / "matched.csv"
            source.write_text('Word,Meaning,Category\nahwe,coffee,Drinks\nmadrase,school,Places\n', encoding="utf-8-sig")
            with patch("lexicon.arwords.dictionary", return_value=ENTRIES):
                result = match_csv(source, output)
            self.assertEqual(result, {"rows": 2, "matched": 1})
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["Arabic"], "قهوة")
            self.assertEqual(rows[0]["Category"], "Drinks")
            self.assertEqual(rows[1]["Arabic"], "")
            self.assertIn("Needs review", rows[1]["Arabic match"])
