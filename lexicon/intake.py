"""Split a pasted lesson into Latin spellings and glosses.

Two shapes can sit in the same paste.

One pair per line (what people type most):
  `6awaret - i developed`  → Arabizi first, English meaning (rest of line)
  `practice - tadreeb`     → English first, one Latin spelling
  `8ararat = decisions`    → spelling, then equals, then the gloss

Same-line chains still work: `practice - tadreeb to train - etdarrab`
or a chain of equals signs. In an equals chain the gloss runs until the next
token that contains an Arabizi digit (2, 3, 5, 6, 7, 8, 9), or the last token
when there is no digit (romaji). Letter-only words such as "al" stay inside
that phrase once the digit has started it.
"""

from __future__ import annotations

import re

_ARABIZI_DIGITS = frozenset("2356789")
_DASHES = (" - ", " – ", " — ")
# "shasheh- sit" — dash stuck to the spelling, space before the meaning.
_TIGHT_DASH = re.compile(r"(\S)([-–—])(\s+\S)")


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
    if _separator_count(remaining) <= 1:
        return [_parse_one_pair(remaining)]
    pairs: list[tuple[str, str]] = []
    while remaining:
        dash_at, dash_len = _first_dash(remaining)
        equals_at = remaining.find("=")
        if dash_at == -1 and equals_at == -1:
            raise ValueError(f"need a word and a meaning: {remaining!r}")
        if equals_at == -1 or (dash_at != -1 and dash_at < equals_at):
            left = remaining[:dash_at].strip()
            after = remaining[dash_at + dash_len :].strip()
            if not left or not after:
                raise ValueError(f"need a word and a meaning: {remaining!r}")
            if _has_arabizi_digit(left):
                # Arabizi-first pairs keep the whole right side as the meaning.
                pairs.append((left, after))
                return pairs
            spelling, _, after = after.partition(" ")
            if not spelling:
                raise ValueError(f"need a word and a meaning: {remaining!r}")
            pairs.append((spelling, left))
            remaining = after.strip()
            continue
        spelling = remaining[:equals_at].strip()
        gloss, remaining = _cut_equals_gloss(remaining[equals_at + 1 :])
        if not spelling or not gloss:
            raise ValueError(f"need a word and a meaning: {text!r}")
        pairs.append((spelling, gloss))
        remaining = remaining.strip()
    return pairs


def _parse_one_pair(text: str) -> tuple[str, str]:
    dash_at, dash_len = _first_dash(text)
    equals_at = text.find("=")
    if dash_at == -1 and equals_at == -1:
        raise ValueError(f"need a word and a meaning: {text!r}")
    if equals_at != -1 and (dash_at == -1 or equals_at < dash_at):
        spelling = text[:equals_at].strip()
        gloss = text[equals_at + 1 :].strip()
        if not spelling or not gloss:
            raise ValueError(f"need a word and a meaning: {text!r}")
        return spelling, gloss
    left = text[:dash_at].strip()
    right = text[dash_at + dash_len :].strip()
    if not left or not right:
        raise ValueError(f"need a word and a meaning: {text!r}")
    if _arabizi_first(left, right):
        return left, right
    spelling, _, leftover = right.partition(" ")
    if leftover.strip():
        # English - arabizi only takes one spelling token; leftover means they
        # wrote arabizi - multi-word English without a digit on the left.
        return left, right
    if not spelling:
        raise ValueError(f"need a word and a meaning: {text!r}")
    return spelling, left


def _arabizi_first(left: str, right: str) -> bool:
    """True when the dash line is spelling on the left, meaning on the right."""
    if _has_arabizi_digit(left):
        return True
    first_right = right.split()[0] if right.split() else ""
    if _has_arabizi_digit(first_right):
        return False
    if any(char.isspace() for char in right):
        return True
    return False


def _separator_count(text: str) -> int:
    count = text.count("=")
    cursor = 0
    while True:
        at, width = _first_dash(text[cursor:])
        if at == -1:
            break
        count += 1
        cursor += at + max(width, 1)
    return count


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
    if found:
        return min(found)
    tight = _TIGHT_DASH.search(text)
    if tight:
        return tight.start(2), 1
    return -1, 0


def item_kind(spelling: str) -> str:
    return "phrase" if any(char.isspace() for char in spelling) else "word"
