import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.learning import dispatch_post, rule_detail, task_detail, workspace
from lexicon.load import connect
from lexicon.notebook import list_items, save_lesson
from lexicon.prefs import save_language


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "notebook.db"
        self.conn = connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def capture(self, **patch):
        body = {"action": "capture", "title": "Continuous actions", "learned_on": "2026-11-16", "teacher": "New teacher", "words_text": "katab = write", "rules": [{"title": "3am + imperfect", "explanation": "Ongoing action", "example": "3am bektob"}], **patch}
        return dispatch_post(self.conn, "local", body)

    def test_grammar_only_and_all_known_lessons_are_valid(self):
        first = self.capture()
        second = self.capture()
        third = self.capture(words_text="")
        self.assertEqual(first["word_ids"], second["word_ids"])
        self.assertEqual(third["word_ids"], [])
        self.assertEqual(len(list_items(self.conn)), 1)
        self.assertEqual(workspace(self.conn, "local")["counts"], {"sessions": 3, "open_homework": 3, "rules": 3})

    def test_capture_is_atomic_on_invalid_rule(self):
        with self.assertRaises(ValueError):
            self.capture(rules=[{"title": "Rule", "explanation": "Explanation", "source": 123}])
        self.assertEqual(list_items(self.conn), [])
        self.assertEqual(workspace(self.conn, "local")["sessions"], [])

    def test_capture_retries_do_not_duplicate_records(self):
        first = self.capture(request_id="one-session")
        self.assertEqual(self.capture(request_id="one-session"), first)
        self.assertEqual(len(workspace(self.conn, "local")["sessions"]), 1)
        with self.assertRaises(ValueError):
            self.capture(request_id="one-session", title="Different payload")

    def test_task_cites_required_word_and_rule(self):
        result = self.capture(goal="talk about work")
        task = task_detail(self.conn, "local", result["task_id"])
        self.assertIn("talk about work", task["prompt"])
        self.assertIn("3am + imperfect", task["prompt"])
        self.assertEqual(task["words"][0]["spelling"], "katab")

    def test_stale_draft_cannot_overwrite_a_newer_device(self):
        task_id = self.capture()["task_id"]
        first = dispatch_post(self.conn, "local", {"action": "draft", "task_id": task_id, "revision": 0, "text": "First device"})
        self.assertEqual(first["revision"], 1)
        with self.assertRaises(ValueError):
            dispatch_post(self.conn, "local", {"action": "draft", "task_id": task_id, "revision": 0, "text": "Stale device"})
        self.assertEqual(task_detail(self.conn, "local", task_id)["draft"], "First device")

    def test_attempts_and_corrections_preserve_original_and_requirements(self):
        result = self.capture()
        body = {"action": "attempt", "task_id": result["task_id"], "revision": 0, "text": "My first sentences", "request_id": "attempt-one"}
        first = dispatch_post(self.conn, "local", body)
        self.assertEqual(dispatch_post(self.conn, "local", body), first)
        dispatch_post(self.conn, "local", {"action": "correction", "attempt_id": first["attempt_id"], "text": "Corrected sentence", "note": "Use bare imperfect", "author": "Teacher notes entered by me"})
        self.conn.execute("UPDATE learning_rules SET explanation = 'Changed rule' WHERE id = ?", (result["rule_ids"][0],))
        self.conn.commit()
        detail = task_detail(self.conn, "local", result["task_id"])
        self.assertEqual(len(detail["attempts"]), 1)
        attempt = detail["attempts"][0]
        self.assertEqual(attempt["text"], "My first sentences")
        self.assertEqual(attempt["requirements"]["rules"][0]["explanation"], "Ongoing action")
        self.assertEqual(attempt["corrections"][0]["text"], "Corrected sentence")

    def test_recall_records_answer_rule_snapshot_and_due_date(self):
        rule_id = self.capture()["rule_ids"][0]
        saved = dispatch_post(self.conn, "local", {"action": "recall", "rule_id": rule_id, "response": "3am plus imperfect", "rating": "recalled"})
        rule = rule_detail(self.conn, "local", rule_id)
        self.assertEqual(rule["due_on"], saved["due_on"])
        self.assertEqual(rule["history"][0]["response"], "3am plus imperfect")
        self.assertEqual(rule["history"][0]["rule_snapshot"]["explanation"], "Ongoing action")

    def test_cross_account_and_cross_language_references_are_rejected(self):
        result = self.capture()
        with self.assertRaises(LookupError):
            task_detail(self.conn, "other", result["task_id"])
        with self.assertRaises(LookupError):
            dispatch_post(self.conn, "other", {"action": "task", "word_ids": result["word_ids"]})
        save_language(self.conn, "japanese")
        self.assertEqual(workspace(self.conn, "local")["sessions"], [])
        with self.assertRaises(LookupError):
            task_detail(self.conn, "local", result["task_id"])

    def test_schema_upgrade_is_repeatable_and_preserves_old_words(self):
        save_lesson(self.conn, "2026-01-01", "ahwe = coffee", embed=lambda rows: [None]*len(rows))
        before = list_items(self.conn)
        self.conn.close()
        self.conn = connect(self.path)
        self.conn.close()
        self.conn = connect(self.path)
        self.assertEqual(list_items(self.conn), before)

    def test_homework_completion_is_explicit_and_can_be_reopened(self):
        task_id = self.capture()["task_id"]
        dispatch_post(self.conn, "local", {"action": "task-status", "task_id": task_id, "status": "done"})
        self.assertEqual(task_detail(self.conn, "local", task_id)["status"], "done")
        dispatch_post(self.conn, "local", {"action": "task-status", "task_id": task_id, "status": "open"})
        self.assertEqual(task_detail(self.conn, "local", task_id)["status"], "open")
