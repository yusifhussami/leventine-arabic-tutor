from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.judge import RateLimiter
from lexicon.load import connect, migrate_notebook_schema
from lexicon.notebook import save_lesson
from lexicon.topics import (
    accept_generated,
    build_topic_prompt,
    forbidden_scene_ids,
    generate_topics,
    list_topics,
    newest_support_words,
    select_topic_words,
    set_topic_status,
)

LESSON = "\n".join(
    [
        "wa7shni = I miss him",
        "imti7an = exam",
        "akhoy = my brother",
        "manchester = Manchester",
        "ta3ban = tired",
        "shoghol = work",
    ]
)

FAMILY = [
    {"id": 1, "spelling": "wa7shni", "gloss": "I miss him"},
    {"id": 2, "spelling": "imti7an", "gloss": "exam"},
    {"id": 3, "spelling": "akhoy", "gloss": "my brother"},
    {"id": 4, "spelling": "manchester", "gloss": "Manchester"},
    {"id": 5, "spelling": "ta3ban", "gloss": "tired"},
    {"id": 6, "spelling": "shoghol", "gloss": "work"},
]

COFFEE = [
    {"id": 1, "spelling": "ahwe", "gloss": "coffee"},
    {"id": 2, "spelling": "bala sukkar", "gloss": "without sugar"},
    {"id": 3, "spelling": "kbeer", "gloss": "large"},
]


def _vectors(glosses):
    return [[0.1, 0.2] for _ in glosses]


class _Response:
    def __init__(self, topics: list[dict]) -> None:
        self._payload = json.dumps(
            {"choices": [{"message": {"content": json.dumps({"topics": topics})}}]}
        ).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _topic(title: str, spellings: list[str] | None = None) -> dict:
    words = spellings or ["wa7shni", "akhoy", "imti7an"]
    by_spelling = {item["spelling"]: item for item in FAMILY}
    return {
        "title": title,
        "why": "Practice I miss him, my brother, and the exam in Manchester while tired from work.",
        "target_words": [
            {
                "spelling": spelling,
                "gloss": by_spelling.get(spelling, {}).get("gloss", "unknown"),
            }
            for spelling in words
        ],
        "prompts": ["keef el imti7an?", "wa7shni akhoy"],
    }


class TopicPromptTests(unittest.TestCase):
    def test_prompt_includes_saved_words_and_forbids_tourist_scenes(self) -> None:
        prompt = build_topic_prompt(
            FAMILY,
            [{"title": "Missing home before the exam", "status": "done"}],
            "arabic",
        )
        self.assertIn("wa7shni = I miss him", prompt)
        self.assertIn("shoghol = work", prompt)
        self.assertIn("LANGUAGE LOCK: arabic", prompt)
        self.assertIn("Yusif", prompt)
        self.assertIn("Amer", prompt)
        self.assertIn("Levantine Arabizi", prompt)
        self.assertIn("FORBIDDEN SCENES", prompt)
        for label in (
            "ordering coffee",
            "taking a taxi",
            "at the restaurant",
            "shopping",
        ):
            self.assertIn(label, prompt)
        self.assertIn("done: Missing home before the exam", prompt)
        self.assertIn("do not repeat", prompt)
        self.assertEqual(
            forbidden_scene_ids(FAMILY),
            ["coffee", "taxi", "restaurant", "shopping"],
        )

    def test_coffee_words_do_not_forbid_a_coffee_scene(self) -> None:
        prompt = build_topic_prompt(COFFEE, [], "arabic")
        self.assertIn("ahwe = coffee", prompt)
        self.assertNotIn("ordering coffee", prompt)
        self.assertIn("taking a taxi", prompt)
        self.assertIn("at the restaurant", prompt)
        self.assertIn("shopping", prompt)
        self.assertNotIn("coffee", forbidden_scene_ids(COFFEE))
        self.assertIn("taxi", forbidden_scene_ids(COFFEE))

    def test_an_old_coffee_word_does_not_unlock_the_scene(self) -> None:
        items = [
            {"id": i, "spelling": f"w{i:03d}", "gloss": f"gloss {i}"}
            for i in range(70, 0, -1)
        ]
        items[-1] = {"id": 1, "spelling": "ahwe", "gloss": "coffee"}
        sample = select_topic_words(items)
        support = newest_support_words(items)
        spellings = [item["spelling"] for item in sample]
        self.assertEqual(spellings[0], "w070")
        self.assertIn("ahwe", spellings)
        self.assertNotIn("ahwe", [item["spelling"] for item in support])
        self.assertLessEqual(len(sample), 60)
        prompt = build_topic_prompt(sample, [], "arabic", support_words=support)
        self.assertIn("w070 = gloss 70", prompt)
        self.assertIn("ahwe = coffee", prompt)
        self.assertIn("ordering coffee", prompt)

    def test_japanese_prompts_ask_for_romaji_not_arabizi(self) -> None:
        words = [
            {"id": 1, "spelling": "tsukareta", "gloss": "tired"},
            {"id": 2, "spelling": "shiken", "gloss": "exam"},
            {"id": 3, "spelling": "ani", "gloss": "older brother"},
        ]
        prompt = build_topic_prompt(words, [], "japanese")
        self.assertIn("LANGUAGE LOCK: japanese", prompt)
        self.assertIn("not Levantine Arabizi", prompt)
        self.assertIn("romaji", prompt)
        self.assertIn("tsukareta = tired", prompt)
        self.assertNotIn("The teacher is Amer", prompt)
        self.assertNotIn("2 for ء", prompt)

    def test_generic_scene_is_rejected_unless_words_support_it(self) -> None:
        generic = {
            "title": "Ordering coffee",
            "why": "Practice ordering coffee at the cafe.",
            "target_words": [
                {"spelling": "wa7shni", "gloss": "I miss him"},
                {"spelling": "imti7an", "gloss": "exam"},
            ],
            "prompts": ["baddi ahwe"],
        }
        accepted, problems, primary_ok = accept_generated(
            {"topics": [generic]},
            FAMILY,
            FAMILY,
            [],
            "arabic",
        )
        self.assertEqual(accepted, [])
        self.assertFalse(primary_ok)
        self.assertTrue(any("ordering coffee" in problem for problem in problems))

        allowed, problems, primary_ok = accept_generated(
            {
                "topics": [
                    {
                        "title": "Ordering coffee for a friend",
                        "why": "Use coffee, without sugar, and large.",
                        "target_words": [
                            {"spelling": "ahwe", "gloss": "coffee"},
                            {"spelling": "kbeer", "gloss": "large"},
                        ],
                        "prompts": ["baddi ahwe bala sukkar"],
                    }
                ]
            },
            COFFEE,
            COFFEE,
            [],
            "arabic",
        )
        self.assertTrue(primary_ok)
        self.assertEqual(problems, [])
        self.assertEqual(allowed[0]["target_words"][0]["spelling"], "ahwe")

    def test_invented_spellings_are_dropped_and_repeats_are_rejected(self) -> None:
        raw = {
            "topics": [
                _topic("Missing your brother before the exam", ["wa7shni", "akhoy", "notaword"]),
            ]
        }
        accepted, _problems, primary_ok = accept_generated(
            raw, FAMILY, FAMILY, [], "arabic"
        )
        self.assertTrue(primary_ok)
        self.assertEqual(
            [word["spelling"] for word in accepted[0]["target_words"]],
            ["wa7shni", "akhoy"],
        )
        self.assertEqual(accepted[0]["target_words"][0]["gloss"], "I miss him")

        again, problems, primary_ok = accept_generated(
            raw,
            FAMILY,
            FAMILY,
            [{"title": "Missing your brother before the exam", "status": "done"}],
            "arabic",
        )
        self.assertEqual(again, [])
        self.assertFalse(primary_ok)
        self.assertTrue(any("repeats" in problem for problem in problems))

    def test_vercel_function_files_stay_within_the_cap(self) -> None:
        root = Path(__file__).resolve().parents[1] / "api"
        files = sorted(path.name for path in root.glob("*.py"))
        self.assertLessEqual(len(files), 12)
        self.assertEqual(len(files), 12)
        self.assertIn("topics.py", files)
        self.assertNotIn("next-lesson.py", files)


class TopicStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")
        save_lesson(self.conn, "2026-10-01", LESSON, embed=_vectors)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _good(self, title: str, spellings: list[str] | None = None) -> dict:
        return _topic(title, spellings)

    def test_generate_persists_done_skip_and_undo(self) -> None:
        calls = {"n": 0}

        def opener(request, timeout):
            calls["n"] += 1
            body = json.loads(request.data.decode())
            prompt = body["messages"][0]["content"]
            self.assertEqual(body["model"], "google/gemini-3.5-flash-lite")
            self.assertEqual(body["response_format"]["type"], "json_schema")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
            self.assertNotIn("test-key", request.data.decode())
            self.assertIn("wa7shni = I miss him", prompt)
            self.assertIn("ordering coffee", prompt)
            self.assertIn("taking a taxi", prompt)
            if calls["n"] == 1:
                self.assertNotIn("IMPORTANT CORRECTION", prompt)
                return _Response(
                    [
                        {
                            "title": "Ordering coffee",
                            "why": "Practice ordering coffee.",
                            "target_words": [
                                {"spelling": "wa7shni", "gloss": "I miss him"},
                                {"spelling": "akhoy", "gloss": "my brother"},
                            ],
                            "prompts": ["ahwe law sama7t"],
                        }
                    ]
                )
            self.assertIn("IMPORTANT CORRECTION", prompt)
            return _Response(
                [
                    self._good("Missing your brother before the exam"),
                    self._good("Tired after work in Manchester", ["ta3ban", "shoghol", "manchester"]),
                ]
            )

        saved = generate_topics(
            self.conn,
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
        )
        self.assertEqual(calls["n"], 2)
        self.assertEqual(saved["primary"]["title"], "Missing your brother before the exam")
        self.assertEqual(saved["primary"]["status"], "suggested")
        self.assertEqual(saved["primary"]["role"], "primary")
        self.assertEqual(
            [word["spelling"] for word in saved["primary"]["target_words"]],
            ["wa7shni", "akhoy", "imti7an"],
        )
        self.assertEqual(len(saved["alternates"]), 1)
        self.assertEqual(saved["alternates"][0]["role"], "alternate")

        row = self.conn.execute(
            "SELECT status, payload, target_words, title FROM lesson_topics ORDER BY id ASC"
        ).fetchone()
        self.assertEqual(row["status"], "suggested")
        self.assertEqual(row["title"], saved["primary"]["title"])
        payload = json.loads(row["payload"])
        self.assertIn("exam", payload["why"])
        self.assertEqual(json.loads(row["target_words"])[0]["spelling"], "wa7shni")
        self.assertIn("id", json.loads(row["target_words"])[0])

        listed = list_topics(self.conn)
        self.assertEqual(
            [item["title"] for item in listed],
            [
                "Missing your brother before the exam",
                "Tired after work in Manchester",
            ],
        )
        done = set_topic_status(self.conn, saved["primary"]["id"], "done")
        self.assertEqual(done["status"], "done")
        self.assertEqual(
            [item["id"] for item in list_topics(self.conn, status="done")],
            [saved["primary"]["id"]],
        )
        skipped = set_topic_status(self.conn, saved["alternates"][0]["id"], "skipped")
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(list_topics(self.conn, status="suggested"), [])
        undone = set_topic_status(self.conn, saved["primary"]["id"], "suggested")
        self.assertEqual(undone["status"], "suggested")
        with self.assertRaises(ValueError):
            set_topic_status(self.conn, saved["primary"]["id"], "later")
        with self.assertRaises(LookupError):
            set_topic_status(self.conn, saved["primary"]["id"], "done", user_id="someone-else")
        self.assertEqual(list_topics(self.conn, user_id="someone-else"), [])

    def test_next_prompt_avoids_a_done_topic(self) -> None:
        def first(request, timeout):
            return _Response([self._good("Missing your brother before the exam")])

        saved = generate_topics(
            self.conn,
            "test-key",
            first,
            pace=RateLimiter(min_interval=0),
        )
        set_topic_status(self.conn, saved["primary"]["id"], "done")

        def second(request, timeout):
            prompt = json.loads(request.data.decode())["messages"][0]["content"]
            self.assertIn("done: Missing your brother before the exam", prompt)
            self.assertIn("do not repeat", prompt)
            return _Response(
                [self._good("Tired after work in Manchester", ["ta3ban", "shoghol", "manchester"])]
            )

        again = generate_topics(
            self.conn,
            "test-key",
            second,
            pace=RateLimiter(min_interval=0),
        )
        self.assertEqual(again["primary"]["title"], "Tired after work in Manchester")
        titles = [item["title"] for item in list_topics(self.conn, status="done")]
        self.assertEqual(titles, ["Missing your brother before the exam"])

    def test_topics_follow_the_learning_language(self) -> None:
        save_lesson(
            self.conn,
            "2026-10-02",
            "tired - tsukareta\nexam - shiken\nbrother - ani",
            embed=_vectors,
            language="japanese",
        )

        def opener(request, timeout):
            prompt = json.loads(request.data.decode())["messages"][0]["content"]
            self.assertIn("tsukareta = tired", prompt)
            self.assertNotIn("wa7shni", prompt)
            self.assertIn("not Levantine Arabizi", prompt)
            return _Response(
                [
                    {
                        "title": "Tired before the exam",
                        "why": "He is tired and has an exam, and wants to tell his older brother.",
                        "target_words": [
                            {"spelling": "tsukareta", "gloss": "tired"},
                            {"spelling": "shiken", "gloss": "exam"},
                            {"spelling": "ani", "gloss": "older brother"},
                        ],
                        "prompts": ["kyou wa totemo tsukareta"],
                    }
                ]
            )

        saved = generate_topics(
            self.conn,
            "test-key",
            opener,
            pace=RateLimiter(min_interval=0),
            language="japanese",
        )
        self.assertEqual(saved["language"], "japanese")
        self.assertEqual(list_topics(self.conn, language="arabic"), [])
        self.assertEqual(len(list_topics(self.conn, language="japanese")), 1)
        with self.assertRaises(LookupError):
            set_topic_status(
                self.conn,
                saved["primary"]["id"],
                "done",
                language="arabic",
            )

    def test_too_few_words_does_not_call_the_model(self) -> None:
        conn = connect(Path(self.tmp.name) / "empty.db")
        try:
            save_lesson(conn, "2026-10-01", "bas = but", embed=_vectors)

            def opener(request, timeout):
                raise AssertionError(request.data)

            with self.assertRaisesRegex(ValueError, "save a few words first"):
                generate_topics(
                    conn,
                    "test-key",
                    opener,
                    pace=RateLimiter(min_interval=0),
                )
        finally:
            conn.close()

    def test_migrate_adds_the_topic_table_on_an_older_sqlite_file(self) -> None:
        self.conn.execute("DROP TABLE lesson_topics")
        self.conn.commit()
        migrate_notebook_schema(self.conn)
        self.conn.execute("SELECT id, status, payload FROM lesson_topics")


if __name__ == "__main__":
    unittest.main()
