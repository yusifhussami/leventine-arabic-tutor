import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from lexicon.load import connect
from lexicon.notebook import list_items, save_lesson
from lexicon.wordbook import dictionary_entry, family, save_dictionary_word, save_family, search_dictionary, suggest_family


ENTRY = {"id": 1, "arabic": "كتب", "meaning": "write", "url": "https://www.arwords.com/words/view/1", "forms": [{"arabic": "كتب", "translit": "katab", "conjugation": "perf.", "dialect": "Leb."}]}


class WordbookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name)/"words.db")
        self.patch = patch("lexicon.wordbook._catalogue", return_value=[(ENTRY, ["كتب", "write", "katab"])])
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.conn.close()
        self.tmp.cleanup()

    def test_dictionary_search_handles_english_arabic_and_arabizi_without_writes(self):
        for query in ("write", "كَتَب", "katab"):
            self.assertEqual(search_dictionary(query)["entries"][0]["id"], 1)
        self.assertEqual(list_items(self.conn), [])

    def test_saving_is_explicit_idempotent_and_keeps_arabic_source(self):
        self.assertEqual(list_items(self.conn), [])
        first = save_dictionary_word(self.conn, "local", {"entry_id": 1, "form_index": 0})
        again = save_dictionary_word(self.conn, "local", {"entry_id": 1, "form_index": 0})
        self.assertEqual(first["item_id"], again["item_id"])
        self.assertTrue(again["already_saved"])
        self.assertEqual(list_items(self.conn)[0]["arabic_source"], "arwords")

    def test_family_sources_and_revision_conflicts(self):
        item_id = save_dictionary_word(self.conn, "local", {"entry_id": 1})["item_id"]
        form = {"kind": "continuous", "source": "teacher", "arabic": "عم يكتب", "arabizi": "3am yektob", "meaning": "is writing", "subject": "he", "example": "Teacher example"}
        saved = save_family(self.conn, "local", {"item_id": item_id, "revision": 0, "forms": [form]})
        self.assertEqual(saved["forms"][0]["kind"], "continuous")
        with self.assertRaises(ValueError):
            save_family(self.conn, "local", {"item_id": item_id, "revision": 0, "forms": []})
        self.assertEqual(len(family(self.conn, "local", item_id)["forms"]), 1)
        with self.assertRaises(LookupError):
            family(self.conn, "other", item_id)

    def test_missing_forms_are_not_invented_on_network_failure(self):
        bare = {**ENTRY, "forms": []}
        with patch("lexicon.wordbook._catalogue", return_value=[(bare, ["كتب", "write"])]):
            data = dictionary_entry(self.conn, 1, opener=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
        self.assertEqual(data["forms"], [])
        self.assertIn("notice", data)

    def test_model_forms_are_unverified_and_do_not_overwrite_saved_family(self):
        item_id = save_dictionary_word(self.conn, "local", {"entry_id": 1})["item_id"]
        payload = {"forms": [{"kind": "past", "arabic": "كتب", "arabizi": "katab", "meaning": "wrote", "subject": "he", "example": "Original example"}]}
        caller = lambda *a, **k: {"choices": [{"message": {"content": json.dumps(payload)}}]}
        result = suggest_family(self.conn, "local", item_id, complete_fn=caller, api_key="test")
        self.assertEqual(result["forms"][0]["source"], "suggestion")
        self.assertEqual(family(self.conn, "local", item_id)["forms"], [])
