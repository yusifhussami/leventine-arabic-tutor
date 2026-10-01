"""Split a pasted lesson into Arabizi spellings and English glosses.

A line with one equals sign is one pair. A line with several equals signs
is a chain: the English gloss runs until the next token that contains an
Arabizi digit (2, 3, 5, 6, 7, 8, 9). Letter-only words such as "al" stay
inside the phrase once that digit has started it.
"""

from __future__ import annotations

_ARABIZI_DIGITS = frozenset("2356789")


def parse_lesson_text(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("lesson text is empty")
    if len(lines) > 1 and all(line.count("=") == 1 for line in lines):
        return [_one_pair(line) for line in lines]
    return _parse_chain(" ".join(lines))


def _one_pair(line: str) -> tuple[str, str]:
    spelling, gloss = line.split("=", 1)
    spelling, gloss = spelling.strip(), gloss.strip()
    if not spelling or not gloss:
        raise ValueError(f"need a word and a meaning: {line!r}")
    return spelling, gloss


def _parse_chain(text: str) -> list[tuple[str, str]]:
    parts = [part.strip() for part in text.split("=")]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        raise ValueError("need word = meaning")
    spelling = parts[0]
    pairs: list[tuple[str, str]] = []
    for chunk in parts[1:-1]:
        gloss, next_spelling = _split_gloss_and_next(chunk)
        if not gloss or not next_spelling:
            raise ValueError(f"could not separate the meaning from the next word: {chunk!r}")
        pairs.append((spelling, gloss))
        spelling = next_spelling
    gloss = parts[-1].strip()
    if not spelling or not gloss:
        raise ValueError("the last pair needs a word and a meaning")
    pairs.append((spelling, gloss))
    return pairs


def _split_gloss_and_next(chunk: str) -> tuple[str, str]:
    tokens = chunk.split()
    for index, token in enumerate(tokens):
        if any(char in _ARABIZI_DIGITS for char in token):
            return " ".join(tokens[:index]), " ".join(tokens[index:])
    return " ".join(tokens), ""


def item_kind(spelling: str) -> str:
    return "phrase" if any(char.isspace() for char in spelling) else "word"
