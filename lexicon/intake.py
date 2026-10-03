"""Split a pasted lesson into Arabizi spellings and English glosses.

Two shapes can sit in the same paste. `practice - tadreeb` is English, then
a dash, then one Arabizi word. `8ararat = decisions` is Arabizi, then equals,
then English. A chain of equals signs still works: the English gloss runs
until the next token that contains an Arabizi digit (2, 3, 5, 6, 7, 8, 9).
Letter-only words such as "al" stay inside that phrase once the digit has
started it.
"""

from __future__ import annotations

_ARABIZI_DIGITS = frozenset("2356789")
_DASHES = (" - ", " – ", " — ")


def parse_lesson_text(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("lesson text is empty")
    pairs: list[tuple[str, str]] = []
    for line in lines:
        pairs.extend(_parse_mixed(line))
    return pairs


def _parse_mixed(text: str) -> list[tuple[str, str]]:
    remaining = " ".join(text.split())
    pairs: list[tuple[str, str]] = []
    while remaining:
        dash_at, dash_len = _first_dash(remaining)
        equals_at = remaining.find("=")
        if dash_at == -1 and equals_at == -1:
            raise ValueError(f"need a word and a meaning: {remaining!r}")
        if equals_at == -1 or (dash_at != -1 and dash_at < equals_at):
            gloss = remaining[:dash_at].strip()
            after = remaining[dash_at + dash_len :].strip()
            spelling, _, after = after.partition(" ")
            if not gloss or not spelling:
                raise ValueError(f"need a word and a meaning: {remaining!r}")
            pairs.append((spelling, gloss))
            remaining = after.strip()
            continue
        spelling = remaining[:equals_at].strip()
        gloss, remaining = _cut_equals_gloss(remaining[equals_at + 1 :])
        if not spelling or not gloss:
            raise ValueError(f"need a word and a meaning: {text!r}")
        pairs.append((spelling, gloss))
        remaining = remaining.strip()
    return pairs


def _cut_equals_gloss(right: str) -> tuple[str, str]:
    right = right.strip()
    equals_at = right.find("=")
    if equals_at == -1:
        return right, ""
    before = right[:equals_at]
    gloss, next_spelling = _gloss_and_next_spelling(before)
    return gloss, f"{next_spelling}{right[equals_at:]}".strip()


def _gloss_and_next_spelling(before_equals: str) -> tuple[str, str]:
    tokens = before_equals.split()
    if not tokens:
        return "", ""
    start = next(
        (index for index, token in enumerate(tokens) if _has_arabizi_digit(token)),
        len(tokens) - 1,
    )
    return " ".join(tokens[:start]).strip(), " ".join(tokens[start:]).strip()


def _has_arabizi_digit(token: str) -> bool:
    return any(char in _ARABIZI_DIGITS for char in token)


def _first_dash(text: str) -> tuple[int, int]:
    found = [(text.find(sep), len(sep)) for sep in _DASHES if text.find(sep) != -1]
    if not found:
        return -1, 0
    return min(found)


def item_kind(spelling: str) -> str:
    return "phrase" if any(char.isspace() for char in spelling) else "word"
