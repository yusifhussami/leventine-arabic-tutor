import io
import json
import sqlite3
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from lexicon.cards import (
    answer,
    card_settings,
    create_word_deck,
    import_apkg,
    learn_more,
    list_decks,
    save_card_settings,
    study,
    sync_words_for_user,
)
from lexicon.load import connect
from lexicon.notebook import list_items, save_lesson
from lexicon.prefs import save_language

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def _embed(glosses):
    return [[0.1, 0.2, 0.3] for _ in glosses]


def _anki_package() -> bytes:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE col (
            id integer primary key,
            crt integer not null,
            mod integer not null,
            scm integer not null,
            ver integer not null,
            dty integer not null,
            usn integer not null,
            ls integer not null,
            conf text not null,
            models text not null,
            decks text not null,
            dconf text not null,
            tags text not null
        );
        CREATE TABLE notes (
            id integer primary key,
            guid text not null,
            mid integer not null,
            mod integer not null,
            usn integer not null,
            tags text not null,
            flds text not null,
            sfld text not null,
            csum integer not null,
            flags integer not null,
            data text not null
        );
        CREATE TABLE cards (
            id integer primary key,
            nid integer not null,
            did integer not null,
            ord integer not null,
            mod integer not null,
            usn integer not null,
            type integer not null,
            queue integer not null,
            due integer not null,
            ivl integer not null,
            factor integer not null,
            reps integer not null,
            lapses integer not null,
            left integer not null,
            odue integer not null,
            odid integer not null,
            flags integer not null,
            data text not null
        );
        """
    )
    models = {
        "1": {
            "id": 1,
            "name": "Basic (and reversed card)",
            "type": 0,
            "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}],
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": "{{Front}}",
                    "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                },
                {
                    "name": "Card 2",
                    "ord": 1,
                    "qfmt": "{{Back}}",
                    "afmt": "{{FrontSide}}<hr id=answer>{{Front}}",
                },
            ],
        },
        "2": {
            "id": 2,
            "name": "Cloze",
            "type": 1,
            "flds": [{"name": "Text", "ord": 0}],
            "tmpls": [
                {
                    "name": "Cloze",
                    "ord": 0,
                    "qfmt": "{{cloze:Text}}",
                    "afmt": "{{cloze:Text}}",
                }
            ],
        },
    }
    decks = {
        "10": {"id": 10, "name": "Verbs", "conf": 1, "dyn": 0},
        "11": {"id": 11, "name": "Filtered", "conf": 1, "dyn": 1},
    }
    dconf = {"1": {"id": 1, "desiredRetention": 0.9, "fsrsWeights": []}}
    conn.execute(
        "INSERT INTO col VALUES (1, ?, 0, 0, 11, 0, 0, 0, '{}', ?, ?, ?, '{}')",
        (
            int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()),
            json.dumps(models),
            json.dumps(decks),
            json.dumps(dconf),
        ),
    )
    conn.execute(
        "INSERT INTO notes VALUES (1, 'a', 1, 0, 0, '', ?, 'cat', 0, 0, '')",
        ("cat\x1fdog",),
    )
    conn.execute(
        "INSERT INTO notes VALUES (2, 'b', 2, 0, 0, '', ?, 'The cat', 0, 0, '')",
        ("The {{c1::cat}} sat",),
    )
    # Review card with FSRS memory, a reversed new card, a cloze, and a suspended card.
    conn.execute(
        "INSERT INTO cards VALUES (1, 1, 10, 0, 0, 0, 2, 2, 100, 12, 2500, 5, 0, 0, 0, 0, 0, ?)",
        ('{"s": 12.5, "d": 4.2}',),
    )
    conn.execute(
        "INSERT INTO cards VALUES (2, 1, 10, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, '')"
    )
    conn.execute(
        "INSERT INTO cards VALUES (3, 2, 10, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, '')"
    )
    conn.execute(
        "INSERT INTO cards VALUES (4, 1, 11, 0, 0, 0, 2, -1, 10, 3, 2500, 1, 0, 0, 0, 0, 0, '')"
    )
    conn.commit()
    script = "\n".join(conn.iterdump())
    conn.close()
    return _zip_sqlite(script)


def _zip_sqlite(script: str, name: str = "collection.anki21") -> bytes:
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=".anki2") as handle:
        built = sqlite3.connect(handle.name)
        built.executescript(script)
        built.commit()
        built.close()
        handle.seek(0)
        payload = handle.read()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(name, payload)
        zipped.writestr("media", "{}")
    return archive.getvalue()


class CardDeckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "lexicon.db")
        save_lesson(
            self.conn,
            "2026-10-01",
            "keefak = how are you\nshukran = thank you",
            embed=_embed,
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_a_word_deck_uses_saved_words_and_fsrs(self) -> None:
        items = list_items(self.conn)
        listed = list_decks(self.conn, "local", now=NOW)
        self.assertTrue(listed["has_words"])
        self.assertEqual(listed["words"][0]["name"], "My Words")
        deck = create_word_deck(
            self.conn,
            "local",
            "Greetings",
            [item["id"] for item in items],
            now=NOW,
        )
        self.assertEqual(deck["deck"]["name"], "Greetings")
        self.assertEqual(deck["deck"]["source"], "words")
        self.assertEqual(deck["due"], 2)
        self.assertEqual(deck["card"]["front"], items[0]["spelling"])
        labels = [button["interval"] for button in deck["card"]["buttons"]]
        self.assertEqual(labels[:3], ["1m", "6m", "10m"])
        self.assertTrue(labels[3].endswith("d"))
        first_id = deck["card"]["id"]
        nxt = answer(self.conn, "local", deck["deck"]["id"], first_id, 3, now=NOW)
        self.assertNotEqual(nxt["card"]["id"], first_id)
        # Finish the other new card, then Anki learn-ahead should bring the
        # 10m learning card back immediately instead of making you wait.
        nxt = answer(self.conn, "local", deck["deck"]["id"], nxt["card"]["id"], 3, now=NOW)
        self.assertEqual(nxt["card"]["id"], first_id)
        # Second Good on a learning card graduates to a day interval.
        good = next(button for button in nxt["card"]["buttons"] if button["rating"] == 3)
        self.assertTrue(good["interval"].endswith("d"))

    def test_someone_elses_word_cannot_enter_the_deck(self) -> None:
        item_id = list_items(self.conn)[0]["id"]
        with self.assertRaises(ValueError):
            create_word_deck(self.conn, "other", "Mine", [item_id], now=NOW)

    def test_words_deck_auto_updates_when_new_words_are_saved(self) -> None:
        listed = list_decks(self.conn, "local", now=NOW)
        self.assertEqual(len(listed["words"]), 1)
        deck_id = listed["words"][0]["id"]
        before = study(self.conn, "local", deck_id, now=NOW)
        self.assertEqual(before["due"], 2)
        save_lesson(
            self.conn,
            "2026-10-02",
            "marhaba = hello",
            embed=_embed,
        )
        after = study(self.conn, "local", deck_id, now=NOW)
        self.assertEqual(after["due"], 3)
        fronts = set()
        session = after
        seen = set()
        guard = 0
        while session["card"] and guard < 10:
            fronts.add(session["card"]["front"])
            if session["card"]["id"] in seen:
                break
            seen.add(session["card"]["id"])
            session = answer(self.conn, "local", deck_id, session["card"]["id"], 4, now=NOW)
            guard += 1
        self.assertIn("marhaba", fronts)
        synced = sync_words_for_user(self.conn, "local", now=NOW)
        self.assertEqual(synced["id"], deck_id)

    def test_anki_import_stays_out_of_the_notebook(self) -> None:
        before = len(list_items(self.conn))
        saved = import_apkg(self.conn, _anki_package(), "local", now=NOW)
        self.assertEqual(len(list_items(self.conn)), before)
        self.assertEqual(saved["count"], 1)
        self.assertEqual(saved["decks"][0]["name"], "Verbs")
        listed = list_decks(self.conn, "local", now=NOW)
        self.assertEqual(listed["anki"][0]["name"], "Verbs")
        self.assertEqual(listed["words"][0]["name"], "My Words")
        save_language(self.conn, "japanese")
        switched = list_decks(self.conn, "local", now=NOW)
        self.assertEqual(switched["anki"][0]["name"], "Verbs")
        self.assertEqual(switched["words"], [])
        save_language(self.conn, "arabic")
        deck_id = saved["decks"][0]["id"]
        session = study(self.conn, "local", deck_id, now=NOW)
        fronts = set()
        seen = set()
        guard = 0
        while session["card"] and guard < 10:
            fronts.add(session["card"]["front"])
            if session["card"]["id"] in seen:
                break
            seen.add(session["card"]["id"])
            # Rate Easy so the card leaves the queue instead of returning in a minute.
            session = answer(self.conn, "local", deck_id, session["card"]["id"], 4, now=NOW)
            guard += 1
        self.assertIn("cat", fronts)
        self.assertIn("dog", fronts)
        self.assertTrue(any("[" in front for front in fronts))

    def test_a_word_deck_follows_the_learning_language(self) -> None:
        item_id = list_items(self.conn)[0]["id"]
        create_word_deck(self.conn, "local", "Arabic", [item_id], now=NOW)
        save_language(self.conn, "japanese")
        hidden = list_decks(self.conn, "local", now=NOW)
        self.assertEqual(hidden["words"], [])
        save_language(self.conn, "arabic")
        shown = list_decks(self.conn, "local", now=NOW)
        self.assertEqual(shown["words"][0]["name"], "Arabic")

    def test_settings_flip_the_prompt_and_remember_the_timer(self) -> None:
        items = list_items(self.conn)
        opened = card_settings(self.conn, "local")
        self.assertEqual(opened["side"], "word")
        self.assertFalse(opened["timer"])
        self.assertEqual(opened["new_per_day"], 20)
        self.assertEqual(opened["prompt_label"], "Arabic")
        self.assertEqual(opened["preview_prompt"], items[0]["spelling"])
        self.assertEqual(opened["preview_answer"], items[0]["gloss"])
        self.assertFalse(opened["preview_example"])
        deck = create_word_deck(self.conn, "local", "Greetings", [items[0]["id"]], now=NOW)
        self.assertEqual(deck["card"]["front"], items[0]["spelling"])
        self.assertEqual(deck["settings"]["side"], "word")
        saved = save_card_settings(self.conn, "local", {"side": "meaning", "timer": True})
        self.assertEqual(saved["preview_prompt"], items[0]["gloss"])
        self.assertEqual(saved["preview_answer"], items[0]["spelling"])
        self.assertTrue(saved["timer"])
        flipped = study(self.conn, "local", deck["deck"]["id"], now=NOW)
        self.assertEqual(flipped["card"]["front"], items[0]["gloss"])
        self.assertEqual(flipped["card"]["back"], items[0]["spelling"])
        self.assertTrue(list_decks(self.conn, "local", now=NOW)["settings"]["timer"])
        save_card_settings(self.conn, "other", {"side": "word", "timer": False})
        self.assertEqual(card_settings(self.conn, "local")["side"], "meaning")
        with self.assertRaises(ValueError):
            save_card_settings(self.conn, "local", {"side": "both"})

    def test_new_cards_per_day_limits_the_queue(self) -> None:
        items = list_items(self.conn)
        deck = create_word_deck(
            self.conn,
            "local",
            "Greetings",
            [item["id"] for item in items],
            now=NOW,
        )
        self.assertEqual(deck["due"], 2)
        self.assertEqual(deck["new_per_day"], 20)
        self.assertEqual(deck["new_left"], 2)
        saved = save_card_settings(self.conn, "local", {"new_per_day": 1})
        self.assertEqual(saved["new_per_day"], 1)
        limited = study(self.conn, "local", deck["deck"]["id"], now=NOW)
        self.assertEqual(limited["due"], 1)
        self.assertEqual(limited["new_per_day"], 1)
        self.assertEqual(limited["new_left"], 1)
        self.assertEqual(limited["settings"]["new_per_day"], 1)
        first = limited["card"]["id"]
        answered = answer(self.conn, "local", deck["deck"]["id"], first, 3, now=NOW)
        # New-card quota is spent, but Anki learn-ahead still shows the learning card.
        self.assertEqual(answered["card"]["id"], first)
        self.assertEqual(answered["new_done"], 1)
        self.assertEqual(answered["new_left"], 0)
        # Raising the limit immediately opens more new cards today.
        save_card_settings(self.conn, "local", {"new_per_day": 5})
        more = study(self.conn, "local", deck["deck"]["id"], now=NOW)
        self.assertGreaterEqual(more["due"], 1)
        self.assertEqual(more["new_left"], 1)
        self.assertEqual(more["new_per_day"], 5)
        # 0 new/day blocks further unseen cards; learning cards may still appear.
        save_card_settings(self.conn, "local", {"new_per_day": 0})
        blocked = list_decks(self.conn, "local", now=NOW)["words"][0]
        self.assertEqual(blocked["new_left"], 0)
        with self.assertRaises(ValueError):
            save_card_settings(self.conn, "local", {"new_per_day": -1})
        with self.assertRaises(ValueError):
            save_card_settings(self.conn, "local", {"new_per_day": 1000})

    def test_learn_more_raises_todays_limit_only(self) -> None:
        save_card_settings(self.conn, "local", {"new_per_day": 1})
        deck_id = list_decks(self.conn, "local", now=NOW)["words"][0]["id"]
        session = study(self.conn, "local", deck_id, now=NOW)
        session = answer(self.conn, "local", deck_id, session["card"]["id"], 4, now=NOW)
        self.assertIsNone(session["card"])
        self.assertTrue(session["new_tomorrow"])
        more = learn_more(self.conn, "local", deck_id, 20, now=NOW)
        self.assertEqual(more["new_per_day"], 21)
        self.assertEqual(more["new_left"], 1)
        self.assertIsNotNone(more["card"])
        tomorrow = study(self.conn, "local", deck_id, now=NOW + timedelta(days=1))
        self.assertEqual(tomorrow["new_per_day"], 1)
        with self.assertRaises(ValueError):
            learn_more(self.conn, "local", deck_id, 0, now=NOW)

    def test_meaning_side_flips_an_imported_card(self) -> None:
        saved = import_apkg(self.conn, _anki_package(), "local", now=NOW)
        deck_id = saved["decks"][0]["id"]
        plain = study(self.conn, "local", deck_id, now=NOW)
        save_card_settings(self.conn, "local", {"side": "meaning"})
        flipped = study(self.conn, "local", deck_id, now=NOW)
        self.assertEqual(flipped["card"]["front"], plain["card"]["back"])
        self.assertEqual(flipped["card"]["back"], plain["card"]["front"])
        self.assertNotEqual(flipped["card"]["front"], plain["card"]["front"])
