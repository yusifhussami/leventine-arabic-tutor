import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.load import connect
from lexicon.prefs import (
    get_language,
    mic_locale,
    save_language,
    writing_system,
    writing_system_label,
)


class PrefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_default_language_is_arabic(self) -> None:
        self.assertEqual(get_language(self.conn), "arabic")

    def test_japanese_can_be_saved_and_read(self) -> None:
        self.assertEqual(save_language(self.conn, "japanese"), "japanese")
        self.assertEqual(get_language(self.conn), "japanese")
        self.assertEqual(save_language(self.conn, "arabic"), "arabic")
        self.assertEqual(get_language(self.conn), "arabic")

    def test_last_saved_language_wins(self) -> None:
        save_language(self.conn, "arabic")
        save_language(self.conn, "japanese")
        save_language(self.conn, "arabic")
        self.assertEqual(get_language(self.conn), "arabic")
        save_language(self.conn, "japanese")
        self.assertEqual(get_language(self.conn), "japanese")

    def test_legacy_aliases_still_work(self) -> None:
        self.assertEqual(save_language(self.conn, "ja"), "japanese")
        self.assertEqual(get_language(self.conn), "japanese")
        self.assertEqual(save_language(self.conn, "en"), "arabic")

    def test_unknown_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_language(self.conn, "french")
        self.assertEqual(get_language(self.conn), "arabic")

    def test_learning_language_drives_spelling_and_mic(self) -> None:
        self.assertEqual(writing_system("arabic"), "arabizi")
        self.assertEqual(writing_system("japanese"), "romaji")
        self.assertEqual(writing_system_label("japanese"), "romaji")
        self.assertEqual(writing_system_label("arabic"), "Arabizi")
        self.assertEqual(mic_locale("arabic"), "ar-SA")
        self.assertEqual(mic_locale("japanese"), "ja-JP")
