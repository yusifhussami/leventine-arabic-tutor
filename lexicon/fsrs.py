"""Anki's FSRS-6 scheduler, with Anki's default learning steps.

Memory updates follow FSRS-6 (the scheduler in current Anki): initial stability,
difficulty with mean reversion, recall and lapse stability, and the same-day
short-term update. When a card is still in learning, the wait until the next
view is Anki's step delay (1 minute, then 10 minutes). Graduating and review
intervals come from FSRS at 90% desired retention, then Anki's fuzz and the
rule that Again < Hard < Good < Easy by at least a day.

Anki leaves (re)learning steps empty only in an experimental mode. A normal
Anki profile still uses 1m 10m for new cards and 10m after a lapse, which is
what this module does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# FSRS-6 defaults from open-spaced-repetition/fsrs-rs, the build Anki ships.
DEFAULT_WEIGHTS: tuple[float, ...] = (
    0.212,
    1.2931,
    2.3065,
    8.2956,
    6.4133,
    0.8334,
    3.0194,
    0.001,
    1.8722,
    0.1666,
    0.796,
    1.4835,
    0.0614,
    0.2629,
    1.6483,
    0.6014,
    1.8729,
    0.5425,
    0.0912,
    0.0658,
    0.1542,
)

DESIRED_RETENTION = 0.9
MAXIMUM_INTERVAL = 36500
S_MIN = 0.001
S_MAX = 36500.0
# Anki's default new-card steps and the lapse step, in minutes.
LEARNING_STEPS: tuple[float, ...] = (1.0, 10.0)
RELEARNING_STEPS: tuple[float, ...] = (10.0,)
# Anki's default "New cards/day" deck option.
NEW_PER_DAY = 20
MAX_NEW_PER_DAY = 999
# Anki's default learn-ahead limit: when nothing else is due, show learning
# cards up to this many minutes early instead of making you wait.
LEARN_AHEAD_MINUTES = 20
DAY = 86400
ROLLOVER_HOUR = 4

# Anki fuzz bands from rslib/src/scheduler/states/fuzz.rs.
_FUZZ_RANGES = (
    (2.5, 7.0, 0.15),
    (7.0, 20.0, 0.1),
    (20.0, math.inf, 0.05),
)

RATING_AGAIN = 1
RATING_HARD = 2
RATING_GOOD = 3
RATING_EASY = 4
RATINGS = (RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY)


@dataclass(frozen=True)
class Memory:
    stability: float
    difficulty: float


@dataclass(frozen=True)
class Outcome:
    state: str
    stability: float
    difficulty: float
    delay_seconds: int
    scheduled_days: int
    learning_remaining: int
    lapses: int
    interval_label: str


def round_half_away(value: float) -> int:
    """Match Rust's round: halves go away from zero. Python's round goes to even."""
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def normalize_weights(values) -> tuple[float, ...] | None:
    """Accept Anki's 21 FSRS-6 weights, or 19 FSRS-5 weights promoted the way fsrs-rs does."""
    try:
        nums = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if len(nums) == 19:
        nums = nums + (0.0, 0.5)
    if len(nums) != 21 or not all(math.isfinite(number) for number in nums):
        return None
    if not 0.1 <= nums[20] <= 0.8:
        return None
    return nums


def normalize_retention(value) -> float:
    try:
        retention = float(value)
    except (TypeError, ValueError):
        return DESIRED_RETENTION
    if retention <= 0 or retention > 1:
        return DESIRED_RETENTION
    return retention


def _decay_factor(weights: tuple[float, ...]) -> tuple[float, float]:
    decay = -weights[20]
    factor = math.exp(math.log(0.9) / decay) - 1.0
    return decay, factor


def interval_days(stability: float, weights: tuple[float, ...], retention: float) -> float:
    """Days until retrievability falls to the requested retention. At 0.9 this is stability."""
    decay, factor = _decay_factor(weights)
    modifier = (retention ** (1.0 / decay) - 1.0) / factor
    return stability * modifier


def retrievability(elapsed_days: int, stability: float, weights: tuple[float, ...]) -> float:
    decay, factor = _decay_factor(weights)
    return (1.0 + factor * elapsed_days / stability) ** decay


def init_stability(rating: int, weights: tuple[float, ...]) -> float:
    return max(weights[rating - 1], 0.1)


def init_difficulty(rating: int, weights: tuple[float, ...]) -> float:
    return weights[4] - math.exp((rating - 1) * weights[5]) + 1.0


def next_difficulty(difficulty: float, rating: int, weights: tuple[float, ...]) -> float:
    delta = -weights[6] * (rating - 3)
    damped = difficulty + (delta * (10.0 - difficulty) / 9.0)
    # Mean reversion uses the raw Easy difficulty, which can sit below 1, then clamps.
    easy = init_difficulty(RATING_EASY, weights)
    reverted = weights[7] * easy + (1.0 - weights[7]) * damped
    return clamp(reverted, 1.0, 10.0)


def _recall_stability(difficulty: float, stability: float, recall: float, rating: int, weights) -> float:
    hard_penalty = weights[15] if rating == RATING_HARD else 1.0
    easy_bonus = weights[16] if rating == RATING_EASY else 1.0
    grown = stability * (
        1.0
        + math.exp(weights[8])
        * (11.0 - difficulty)
        * stability ** (-weights[9])
        * (math.exp((1.0 - recall) * weights[10]) - 1.0)
        * hard_penalty
        * easy_bonus
    )
    return clamp(grown, S_MIN, S_MAX)


def _forget_stability(difficulty: float, stability: float, recall: float, weights) -> float:
    forgotten = (
        weights[11]
        * difficulty ** (-weights[12])
        * ((stability + 1.0) ** weights[13] - 1.0)
        * math.exp((1.0 - recall) * weights[14])
    )
    # A lapse cannot leave stability higher than the short-term Again ceiling.
    cap = stability / math.exp(weights[17] * weights[18])
    return min(max(forgotten, S_MIN), max(cap, S_MIN))


def _short_term_stability(stability: float, rating: int, weights) -> float:
    sinc = math.exp(weights[17] * (rating - 3 + weights[18])) * stability ** (-weights[19])
    # FSRS-6: same-day Good and Easy cannot shrink stability. Hard and Again can.
    if rating >= RATING_GOOD:
        sinc = max(sinc, 1.0)
    return clamp(stability * sinc, S_MIN, S_MAX)


def next_memory(
    state: Memory | None,
    elapsed_days: int,
    rating: int,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
) -> Memory:
    if state is None:
        return Memory(
            init_stability(rating, weights),
            clamp(init_difficulty(rating, weights), 1.0, 10.0),
        )
    if elapsed_days <= 0:
        stability = _short_term_stability(state.stability, rating, weights)
    elif rating == RATING_AGAIN:
        recall = retrievability(elapsed_days, state.stability, weights)
        stability = _forget_stability(state.difficulty, state.stability, recall, weights)
    else:
        recall = retrievability(elapsed_days, state.stability, weights)
        stability = _recall_stability(state.difficulty, state.stability, recall, rating, weights)
    return Memory(stability, next_difficulty(state.difficulty, rating, weights))


def memory_from_sm2(
    interval: int,
    ease_factor: float,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
) -> Memory:
    """Anki's conversion when a card has an SM-2 interval but no FSRS memory yet."""
    decay, factor = _decay_factor(weights)
    sm2_retention = 0.9
    span = max(int(interval), 1)
    stability = max(span, S_MIN) * factor / (sm2_retention ** (1.0 / decay) - 1.0)
    ease = ease_factor if ease_factor > 1.0 else 2.5
    growth = math.exp(weights[8]) * stability ** (-weights[9]) * (math.exp((1.0 - sm2_retention) * weights[10]) - 1.0)
    if growth == 0 or not math.isfinite(stability):
        return Memory(float(span), clamp(init_difficulty(RATING_GOOD, weights), 1.0, 10.0))
    difficulty = 11.0 - (ease - 1.0) / growth
    if not math.isfinite(difficulty):
        difficulty = init_difficulty(RATING_GOOD, weights)
    return Memory(max(stability, S_MIN), clamp(difficulty, 1.0, 10.0))


def _secs(minutes: float) -> int:
    return int(minutes * 60.0)


def _step_index(total: int, remaining: int) -> int:
    index = max(0, total - (remaining % 1000))
    return min(index, max(0, total - 1))


def _maybe_round_days(seconds: int) -> int:
    if seconds > DAY:
        return round_half_away(seconds / DAY) * DAY
    return seconds


def again_delay(steps: tuple[float, ...]) -> int | None:
    if not steps:
        return None
    return _secs(steps[0])


def good_delay(steps: tuple[float, ...], remaining: int) -> int | None:
    if not steps:
        return None
    index = _step_index(len(steps), remaining)
    if index + 1 >= len(steps):
        return None
    return _secs(steps[index + 1])


def hard_delay(steps: tuple[float, ...], remaining: int) -> int | None:
    """Anki averages the first two steps so Hard is not the same wait as Again."""
    if not steps:
        return None
    index = _step_index(len(steps), remaining)
    current = _secs(steps[index]) if index < len(steps) else _secs(steps[0])
    if index != 0:
        return current
    if len(steps) > 1:
        return _maybe_round_days((current + _secs(steps[1])) // 2)
    longer = min((current * 3) // 2, current + DAY)
    return _maybe_round_days(longer)


def remaining_for_good(steps: tuple[float, ...], remaining: int) -> int:
    index = _step_index(len(steps), remaining)
    return max(0, len(steps) - index - 1)


def normalize_new_per_day(value) -> int:
    """Anki's New cards/day: 0 hides new cards; default is 20."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return NEW_PER_DAY
    return int(clamp(count, 0, MAX_NEW_PER_DAY))


def fuzz_unit(card_id: int, reps: int = 0) -> float:
    """Stable 0–1 factor so the button preview and the saved interval match.

    Anki derives fuzz from the card id and review count so the same answer
    does not always land on the same side of the band.
    """
    mixed = ((int(card_id) + int(reps)) * 2654435761) & 0xFFFFFFFF
    return mixed / 0xFFFFFFFF


def fuzz_delta(interval: float) -> float:
    """Days of fuzz on each side. Matches Anki's fuzz_delta."""
    if interval < 2.5:
        return 0.0
    delta = 1.0
    for start, end, factor in _FUZZ_RANGES:
        delta += factor * max(min(interval, end) - start, 0.0)
    return delta


def fuzz_bounds(interval: float) -> tuple[int, int]:
    delta = fuzz_delta(interval)
    return round_half_away(interval - delta), round_half_away(interval + delta)


def constrained_fuzz_bounds(
    interval: float,
    minimum: int = 1,
    maximum: int = MAXIMUM_INTERVAL,
) -> tuple[int, int]:
    """Anki's constrained_fuzz_bounds: clamp the band, keep at least two days when allowed."""
    maximum = max(1, int(maximum))
    minimum = int(clamp(minimum, 1, maximum))
    capped = clamp(float(interval), float(minimum), float(maximum))
    low, high = fuzz_bounds(capped)
    low = int(clamp(low, minimum, maximum))
    high = int(clamp(high, minimum, maximum))
    if high == low and high > 2 and high < maximum:
        high = low + 1
    return low, high


def with_review_fuzz(
    interval: float,
    card_id: int,
    minimum: int = 1,
    maximum: int = MAXIMUM_INTERVAL,
    reps: int = 0,
) -> int:
    """Anki's with_review_fuzz without load balancing."""
    low, high = constrained_fuzz_bounds(interval, minimum, maximum)
    unit = fuzz_unit(card_id, reps)
    return int(math.floor(low + unit * (1 + high - low)))


def format_interval(seconds: int) -> str:
    if seconds < 30:
        return "<1m"
    if seconds < 3600:
        return f"{round_half_away(seconds / 60)}m"
    if seconds < DAY:
        return f"{round_half_away(seconds / 3600)}h"
    days = max(1, round_half_away(seconds / DAY))
    if days < 30:
        return f"{days}d"
    if days < 365:
        months = days / 30.0
        shown = round_half_away(months * 10) / 10.0
        if abs(shown - round(shown)) < 0.05:
            return f"{int(round(shown))}mo"
        return f"{shown:.1f}mo"
    years = days / 365.0
    shown = round_half_away(years * 10) / 10.0
    if abs(shown - round(shown)) < 0.05:
        return f"{int(round(shown))}yr"
    return f"{shown:.1f}yr"


def scheduler_date(moment: datetime):
    """Anki's day rolls at 04:00, so a review just after midnight is still yesterday."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment.astimezone(timezone.utc) - timedelta(hours=ROLLOVER_HOUR)).date()


def elapsed_scheduler_days(last_review: datetime | None, now: datetime) -> int:
    if last_review is None:
        return 0
    return max(0, (scheduler_date(now) - scheduler_date(last_review)).days)


def review_due(now: datetime, days: int) -> datetime:
    day = scheduler_date(now) + timedelta(days=days)
    return datetime(day.year, day.month, day.day, ROLLOVER_HOUR, tzinfo=timezone.utc)


def _raw_days(stability: float, weights: tuple[float, ...], retention: float) -> int:
    raw = interval_days(stability, weights, retention)
    return int(clamp(float(round_half_away(raw)), 1, MAXIMUM_INTERVAL))


def _order_days(spans: dict[int, int]) -> dict[int, int]:
    """Anki will not let a harder button schedule a longer wait than an easier one."""
    ordered: dict[int, int] = {}
    previous = 0
    for rating in RATINGS:
        if rating not in spans:
            continue
        value = min(MAXIMUM_INTERVAL, max(spans[rating], previous + 1))
        ordered[rating] = value
        previous = value
    return ordered


def _fuzz_review_days(
    raw_spans: dict[int, int],
    previous_days: int,
    card_id: int,
    reps: int,
    fuzz: bool,
) -> dict[int, int]:
    """Fuzz Hard/Good/Easy with Anki's cascading floors; Again is the first floor."""
    if not fuzz:
        return _order_days(raw_spans)
    ordered: dict[int, int] = {}
    floor = 0
    for rating in RATINGS:
        if rating not in raw_spans:
            continue
        minimum = max(1, floor + 1)
        if rating != RATING_AGAIN and previous_days > 0 and raw_spans[rating] > previous_days:
            minimum = max(minimum, previous_days + 1)
        days = with_review_fuzz(raw_spans[rating], card_id, minimum, MAXIMUM_INTERVAL, reps)
        days = min(MAXIMUM_INTERVAL, max(days, minimum))
        ordered[rating] = days
        floor = days
    return ordered


def _steps_for(state: str) -> tuple[float, ...]:
    if state == "relearning":
        return RELEARNING_STEPS
    return LEARNING_STEPS


def _remaining(card: dict) -> int:
    if card["state"] == "new":
        return len(LEARNING_STEPS)
    if card["state"] in ("learning", "relearning"):
        remaining = int(card.get("learning_remaining") or 0)
        return remaining or len(_steps_for(card["state"]))
    return 0


def schedule(
    card: dict,
    now: datetime,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
    retention: float = DESIRED_RETENTION,
    fuzz: bool = True,
) -> dict[int, Outcome]:
    """The four Anki buttons for this card, including the wait each one would set."""
    weights = normalize_weights(weights) or DEFAULT_WEIGHTS
    retention = normalize_retention(retention)
    state = card["state"]
    phase = "learning" if state == "new" else state
    elapsed = 0
    memory = None
    if card.get("stability") is not None and card.get("difficulty") is not None and state != "new":
        memory = Memory(float(card["stability"]), float(card["difficulty"]))
        elapsed = elapsed_scheduler_days(card.get("last_review_at"), now)
    steps = _steps_for(phase)
    remaining = _remaining(card)
    lapses = int(card.get("lapses") or 0)
    stored_days = int(card.get("scheduled_days") or 0)
    card_id = int(card.get("id") or 1)

    memories = {rating: next_memory(memory, elapsed, rating, weights) for rating in RATINGS}
    reps = int(card.get("reps") or 0)
    raw_days = {
        rating: _raw_days(memories[rating].stability, weights, retention) for rating in RATINGS
    }
    # Review cards keep a day interval for every button. Again is shown as the
    # relearning step, but its day interval is what you get after that step,
    # and it is the floor under Hard, Good, and Easy.
    if phase == "review":
        day_spans = _fuzz_review_days(raw_days, stored_days, card_id, reps, fuzz)
    else:
        day_spans = dict(raw_days)
        graduating = {
            rating: raw_days[rating]
            for rating in RATINGS
            if _step_delay(phase, rating, remaining) is None and not (phase == "relearning" and rating == RATING_GOOD)
        }
        if phase == "relearning" and _step_delay(phase, RATING_GOOD, remaining) is None:
            # Good finishes the lapse and returns the interval chosen when you pressed Again.
            lapse_days = max(1, stored_days)
            graduating[RATING_GOOD] = lapse_days
            if RATING_EASY in graduating:
                graduating[RATING_EASY] = max(graduating[RATING_EASY], lapse_days + 1)
        fuzzed = _fuzz_review_days(graduating, stored_days, card_id, reps, fuzz) if graduating else {}
        for rating, days in fuzzed.items():
            day_spans[rating] = days

    return {
        rating: _outcome(
            phase,
            rating,
            memories[rating],
            day_spans[rating],
            remaining,
            lapses,
            steps,
            stored_days,
        )
        for rating in RATINGS
    }


def _step_delay(state: str, rating: int, remaining: int) -> int | None:
    """Seconds until the next view, or None when this rating graduates the card."""
    steps = _steps_for(state)
    if state == "review":
        if rating == RATING_AGAIN and RELEARNING_STEPS:
            return again_delay(RELEARNING_STEPS)
        return None
    if rating == RATING_AGAIN:
        return again_delay(steps)
    if rating == RATING_HARD:
        return hard_delay(steps, remaining)
    if rating == RATING_GOOD:
        return good_delay(steps, remaining)
    return None


def _outcome(
    state: str,
    rating: int,
    memory: Memory,
    days: int,
    remaining: int,
    lapses: int,
    steps: tuple[float, ...],
    stored_days: int,
) -> Outcome:
    delay = _step_delay(state, rating, remaining)
    if state == "review" and rating == RATING_AGAIN:
        lapses += 1
        if delay is not None:
            return Outcome(
                "relearning",
                memory.stability,
                memory.difficulty,
                delay,
                days,
                len(RELEARNING_STEPS),
                lapses,
                format_interval(delay),
            )
    if delay is not None:
        if rating == RATING_AGAIN:
            next_remaining = len(steps)
            kept_days = days if state == "relearning" else 0
        elif rating == RATING_GOOD:
            next_remaining = remaining_for_good(steps, remaining)
            kept_days = stored_days if state == "relearning" else 0
        else:
            next_remaining = remaining
            kept_days = stored_days if state == "relearning" else 0
        return Outcome(
            "relearning" if state == "relearning" else "learning",
            memory.stability,
            memory.difficulty,
            delay,
            kept_days,
            next_remaining,
            lapses,
            format_interval(delay),
        )
    scheduled = days
    if state == "relearning" and rating == RATING_GOOD:
        scheduled = max(1, stored_days)
    return Outcome(
        "review",
        memory.stability,
        memory.difficulty,
        scheduled * DAY,
        scheduled,
        0,
        lapses,
        format_interval(scheduled * DAY),
    )


def due_after(now: datetime, outcome: Outcome) -> datetime:
    if outcome.state == "review":
        return review_due(now, outcome.scheduled_days)
    return now.astimezone(timezone.utc) + timedelta(seconds=outcome.delay_seconds)
