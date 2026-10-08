import math
import unittest
from datetime import datetime, timedelta, timezone

from lexicon.fsrs import (
    DEFAULT_WEIGHTS,
    Memory,
    again_delay,
    constrained_fuzz_bounds,
    format_interval,
    good_delay,
    hard_delay,
    init_difficulty,
    init_stability,
    next_memory,
    schedule,
    with_review_fuzz,
)


NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def _card(**overrides):
    card = {
        "id": 7,
        "state": "new",
        "stability": None,
        "difficulty": None,
        "scheduled_days": 0,
        "learning_remaining": 0,
        "reps": 0,
        "lapses": 0,
        "last_review_at": None,
    }
    card.update(overrides)
    return card


class FsrsTests(unittest.TestCase):
    def test_new_card_matches_anki_fsrs6(self) -> None:
        """Published FSRS-6 first-review states from fsrs-rs, which Anki uses."""
        expected = {
            1: (0.212, 6.4133),
            2: (1.2931, 5.1121707),
            3: (2.3065, 2.118104),
            4: (8.2956, 1.0),
        }
        for rating, (stability, difficulty) in expected.items():
            state = next_memory(None, 0, rating)
            self.assertAlmostEqual(state.stability, stability, places=4)
            self.assertAlmostEqual(state.difficulty, difficulty, places=4)
            self.assertAlmostEqual(state.stability, init_stability(rating, DEFAULT_WEIGHTS), places=6)
            self.assertAlmostEqual(
                state.difficulty,
                min(10.0, max(1.0, init_difficulty(rating, DEFAULT_WEIGHTS))),
                places=4,
            )

    def test_learning_steps_match_anki(self) -> None:
        # Anki's own step table: 1m 10m, first view and second view.
        self.assertEqual(again_delay((1.0, 10.0)), 60)
        self.assertEqual(hard_delay((1.0, 10.0), 2), 330)
        self.assertEqual(good_delay((1.0, 10.0), 2), 600)
        self.assertEqual(hard_delay((1.0, 10.0), 1), 600)
        self.assertIsNone(good_delay((1.0, 10.0), 1))
        self.assertEqual(again_delay((10.0,)), 600)
        self.assertEqual(hard_delay((10.0,), 1), 900)
        self.assertIsNone(good_delay((10.0,), 1))

    def test_new_card_buttons_are_anki_steps_then_easy_days(self) -> None:
        buttons = schedule(_card(), NOW, fuzz=False)
        self.assertEqual(buttons[1].state, "learning")
        self.assertEqual(buttons[1].delay_seconds, 60)
        self.assertEqual(buttons[1].interval_label, "1m")
        self.assertEqual(buttons[2].delay_seconds, 330)
        self.assertEqual(buttons[2].interval_label, "6m")
        self.assertEqual(buttons[3].state, "learning")
        self.assertEqual(buttons[3].delay_seconds, 600)
        self.assertEqual(buttons[3].interval_label, "10m")
        self.assertEqual(buttons[3].learning_remaining, 1)
        self.assertEqual(buttons[4].state, "review")
        self.assertEqual(buttons[4].scheduled_days, 8)
        self.assertEqual(buttons[4].interval_label, "8d")

    def test_good_then_good_graduates(self) -> None:
        first = schedule(_card(), NOW, fuzz=False)[3]
        card = _card(
            state=first.state,
            stability=first.stability,
            difficulty=first.difficulty,
            learning_remaining=first.learning_remaining,
            last_review_at=NOW,
            reps=1,
        )
        second = schedule(card, NOW + timedelta(minutes=10), fuzz=False)[3]
        self.assertEqual(second.state, "review")
        self.assertGreaterEqual(second.scheduled_days, 1)

    def test_review_again_enters_relearning(self) -> None:
        card = _card(
            state="review",
            stability=10.0,
            difficulty=5.0,
            scheduled_days=10,
            last_review_at=NOW - timedelta(days=10),
            reps=4,
        )
        again = schedule(card, NOW, fuzz=False)[1]
        self.assertEqual(again.state, "relearning")
        self.assertEqual(again.delay_seconds, 600)
        self.assertEqual(again.interval_label, "10m")
        self.assertEqual(again.lapses, 1)
        self.assertGreaterEqual(again.scheduled_days, 1)
        hard = schedule(card, NOW, fuzz=False)[2]
        self.assertEqual(hard.state, "review")
        self.assertGreater(hard.scheduled_days, again.scheduled_days)

    def test_same_day_good_does_not_shrink_stability(self) -> None:
        state = Memory(stability=4.0, difficulty=5.0)
        updated = next_memory(state, 0, 3)
        self.assertGreaterEqual(updated.stability, state.stability)
        easy = next_memory(state, 0, 4)
        self.assertGreaterEqual(easy.stability, state.stability)

    def test_same_day_hard_may_shrink_stability(self) -> None:
        # FSRS-6 allows Hard to reduce short-term stability; Good/Easy cannot.
        state = Memory(stability=4.0, difficulty=5.0)
        hard = next_memory(state, 0, 2)
        self.assertLess(hard.stability, state.stability)

    def test_anki_fuzz_bounds_match_published_values(self) -> None:
        self.assertEqual(constrained_fuzz_bounds(2.5, 1, 1000), (2, 4))
        self.assertEqual(constrained_fuzz_bounds(7.0, 1, 1000), (5, 9))
        self.assertEqual(constrained_fuzz_bounds(17.0, 1, 1000), (14, 20))
        self.assertEqual(with_review_fuzz(7.0, card_id=1, minimum=1, maximum=1000, reps=0), with_review_fuzz(7.0, 1, 1, 1000, 0))

    def test_review_buttons_keep_anki_order(self) -> None:
        card = _card(
            state="review",
            stability=10.0,
            difficulty=5.0,
            scheduled_days=10,
            last_review_at=NOW - timedelta(days=10),
            reps=4,
        )
        buttons = schedule(card, NOW, fuzz=True)
        self.assertLess(buttons[1].scheduled_days, buttons[2].scheduled_days)
        self.assertLess(buttons[2].scheduled_days, buttons[3].scheduled_days)
        self.assertLess(buttons[3].scheduled_days, buttons[4].scheduled_days)
        self.assertGreaterEqual(buttons[2].scheduled_days, 11)

    def test_a_lapse_after_a_real_gap_lowers_stability(self) -> None:
        state = next_memory(None, 0, 3)
        later = next_memory(state, 10, 3)
        self.assertGreater(later.stability, state.stability)
        failed = next_memory(later, 40, 1)
        self.assertLess(failed.stability, later.stability)

    def test_fuzz_stays_put_for_a_card(self) -> None:
        card = _card()
        first = schedule(card, NOW)[4].scheduled_days
        second = schedule(card, NOW)[4].scheduled_days
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 1)

    def test_interval_labels(self) -> None:
        self.assertEqual(format_interval(60), "1m")
        self.assertEqual(format_interval(330), "6m")
        self.assertEqual(format_interval(600), "10m")
        self.assertEqual(format_interval(86400), "1d")
        self.assertEqual(format_interval(8 * 86400), "8d")
        self.assertTrue(math.isfinite(next_memory(None, 0, 4).stability))
