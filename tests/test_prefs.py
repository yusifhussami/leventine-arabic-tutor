import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.load import connect
from lexicon.prefs import get_language, save_language, writing_system, writing_system_label


class PrefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_default_language_is_english(self) -> None:
        self.assertEqual(get_language(self.conn), "en")

    def test_japanese_can_be_saved_and_read(self) -> None:
        self.assertEqual(save_language(self.conn, "ja"), "ja")
        self.assertEqual(get_language(self.conn), "ja")
        self.assertEqual(save_language(self.conn, "en"), "en")
        self.assertEqual(get_language(self.conn), "en")

    def test_unknown_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_language(self.conn, "ar")
        self.assertEqual(get_language(self.conn), "en")

    def test_japanese_account_uses_romaji_writing(self) -> None:
        self.assertEqual(writing_system("en"), "arabizi")
        self.assertEqual(writing_system("ja"), "romaji")
        self.assertEqual(writing_system_label("ja"), "romaji")
        self.assertEqual(writing_system_label("en"), "Arabizi")
