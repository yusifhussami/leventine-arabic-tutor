"""Split a pasted lesson into spellings and glosses.

One pair per line is the usual paste.

Arabic (the default) reads both separators the same way. The left side is the
spelling and the right side is the English meaning:

  `eb7as - to search`     → eb7as, to search
  `ahwe - coffee`         → ahwe, coffee
  `b shakel 3aam - generally`
  `8ararat = decisions`   → 8ararat, decisions

`–` and `—` work like `-`. Spaces around the separator are optional.
Hyphens inside an Arabizi spelling stay in the spelling (`3am y-9eer`,
`b-y-a7ko`, `y-eshra7-lak`). A slash or a parenthetical note stays in the
meaning.

Japanese still accepts a meaning-first dash when the right side is one
spelling: `hello - konnichiwa`. Equals stays spelling-first there too.

A same-line English-first chain still works:
`practice - tadreeb to train - etdarrab`, and a chain of equals signs.
In an equals chain the gloss runs until the next token that contains an
Arabizi digit (2, 3, 5, 6, 7, 8, 9), or the last token when there is no
digit (romaji). Letter-only words such as "al" stay inside that phrase once
the digit has started it.
"""

from __future__ import annotations

from lexicon.prefs import normalize_language

_ARABIZI_DIGITS = frozenset("2356789")
# ASCII hyphen and the hyphen characters a notes app may substitute.
# These can also sit inside an Arabizi spelling.
_FLEX_HYPHENS = frozenset("-‐‑")
# Dashes that always separate a spelling from a meaning.
_WIDE_DASHES = frozenset("–—−‒―")
# Short pieces written with a hyphen inside one Arabizi word.
_PREFIXES = frozenset({"b", "y", "m", "t", "n", "k", "l", "w"})
_CLITICS = frozenset(
    {
        "ak",
        "ek",
        "ik",
        "ha",
        "hon",
        "hom",
        "hun",
        "na",
        "ni",
        "kon",
        "kom",
        "kun",
        "lak",
        "lik",
        "lok",
        "lon",
        "li",
        "lo",
        "la",
        "shi",
    }
)


def parse_lesson_text(text: str, language: str | None = None) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("lesson text is empty")
    # Arabic dash lines are spelling-first, the same as equals.
    # Japanese keeps `hello - konnichiwa` (meaning, then one spelling).
    spelling_first = normalize_language(language) != "japanese"
    pairs: list[tuple[str, str]] = []
    for line in lines:
        pairs.extend(_parse_mixed(line, spelling_first=spelling_first))
    return pairs


def _parse_mixed(text: str, *, spelling_first: bool) -> list[tuple[str, str]]:
    remaining = " ".join(text.split())
    if _separator_count(remaining) <= 1:
        return [_parse_one_pair(remaining, spelling_first=spelling_first)]
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
            if _has_arabizi_digit(left) or (spelling_first and _right_is_single_meaning(after)):
                # Arabizi-first: the rest of the line is the meaning, even
                # when that meaning contains another dash.
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


def _parse_one_pair(text: str, *, spelling_first: bool) -> tuple[str, str]:
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
    if spelling_first or _arabizi_first(left, right):
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
    """True when the dash line is spelling on the left and meaning on the right."""
    if _has_arabizi_digit(left):
        return True
    first_right = right.split()[0] if right.split() else ""
    if _has_arabizi_digit(first_right):
        return False
    if any(char.isspace() for char in right):
        return True
    return False


def _right_is_single_meaning(after: str) -> bool:
    """True when another dash sits in the meaning, not in a gloss/spelling chain.

    `coffee - the drink` is one meaning. `tadreeb to train - etdarrab` is the
    old same-line chain and returns False.
    """
    _token, _, rest = after.partition(" ")
    rest = rest.lstrip()
    return bool(rest) and rest[0] in _FLEX_HYPHENS | _WIDE_DASHES


def _separator_count(text: str) -> int:
    count = text.count("=")
    cursor = 0
    spaced = 0
    while True:
        at = _next_spaced_or_wide(text, cursor)
        if at == -1:
            break
        spaced += 1
        cursor = at + 1
    count += spaced
    # `ahwe-coffee` has no spaced dash. A hyphen inside `well-known` does not
    # add a second pair when the line already has ` - `.
    if spaced == 0 and _next_bare(text, 0) != -1:
        count += 1
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
    at = _next_spaced_or_wide(text, 0)
    if at != -1:
        return at, 1
    bare = _next_bare(text, 0)
    if bare != -1:
        return bare, 1
    return -1, 0


def _next_spaced_or_wide(text: str, start: int) -> int:
    for index in range(start, len(text)):
        char = text[index]
        if char in _WIDE_DASHES and _both_sides(text, index):
            return index
        if char in _FLEX_HYPHENS and _is_spaced_hyphen(text, index):
            return index
    return -1


def _next_bare(text: str, start: int) -> int:
    for index in range(start, len(text)):
        if text[index] in _FLEX_HYPHENS and _is_bare_separator(text, index):
            return index
    return -1


def _both_sides(text: str, index: int) -> bool:
    return bool(text[:index].strip()) and bool(text[index + 1 :].strip())


def _is_spaced_hyphen(text: str, index: int) -> bool:
    if text[index] not in _FLEX_HYPHENS or not _both_sides(text, index):
        return False
    before = text[index - 1] if index else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    return before.isspace() or after.isspace()


def _is_bare_separator(text: str, index: int) -> bool:
    if text[index] not in _FLEX_HYPHENS or not _both_sides(text, index):
        return False
    if index == 0 or index + 1 >= len(text):
        return False
    if text[index - 1].isspace() or text[index + 1].isspace():
        return False
    return not _is_internal_hyphen(text, index)


def _is_internal_hyphen(text: str, index: int) -> bool:
    """True when this hyphen is inside one Arabizi spelling."""
    right_chunk = _chunk_after(text, index)
    left_chunk = _chunk_before(text, index)
    if not right_chunk or not left_chunk:
        return False
    if _has_arabizi_digit(right_chunk):
        return True
    if right_chunk.casefold() in _CLITICS:
        return True
    if left_chunk.casefold() in _PREFIXES and (
        right_chunk.casefold() in _PREFIXES or _has_arabizi_digit(right_chunk)
    ):
        return True
    return False


def _chunk_after(text: str, index: int) -> str:
    end = index + 1
    while end < len(text) and _in_chunk(text[end]):
        end += 1
    return text[index + 1 : end]


def _chunk_before(text: str, index: int) -> str:
    start = index
    while start > 0 and _in_chunk(text[start - 1]):
        start -= 1
    return text[start:index]


def _in_chunk(char: str) -> bool:
    return char.isalnum() or char in "'’"


def item_kind(spelling: str) -> str:
    return "phrase" if any(char.isspace() for char in spelling) else "word"
