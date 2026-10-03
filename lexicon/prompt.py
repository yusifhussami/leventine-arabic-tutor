"""Assemble the prompt a tutor model will receive. This does not call a model."""

from __future__ import annotations

from lexicon.practice import PracticeCard, PracticeSession
from lexicon.prefs import DEFAULT_LANGUAGE, learning_label, writing_system_label


def build_prompt(
    session: PracticeSession,
    card: PracticeCard,
    sentence: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """Context for judging one sentence against one card from this session.

    Other cards and grammar notes are only from the same lesson day. A card
    from another session is rejected so the prompt cannot mix two lessons.
    Comments stay English. Spelling system follows the learning language.
    """
    text = sentence.strip()
    if not text:
        raise ValueError("sentence is empty")
    if card not in session.cards:
        raise ValueError("card is not in this session")

    others = "\n".join(
        f"- {other.word}: {other.meaning}" for other in session.cards if other != card
    ) or "(none)"
    notes = "\n".join(
        f"- {note.word or '(no headword)'}: {note.meaning}" for note in session.notes
    ) or "(none)"
    latin = writing_system_label(language)
    target = learning_label(language)
    return (
        f"You are a {target} tutor using {latin}.\n"
        "The learner is practicing one target from their latest lesson.\n"
        "Judge whether their sentence uses the target in a way that fits the meaning.\n"
        "Use the other lesson items and grammar notes only as context.\n"
        "Do not invent a sentence for them.\n"
        f"Write the comment in English. Do not rewrite the learner's {latin}.\n"
        "\n"
        f"Target ({card.kind}): {card.word}\n"
        f"Meaning: {card.meaning}\n"
        "\n"
        "Learner's sentence:\n"
        f"{text}\n"
        "\n"
        "Other items from this lesson:\n"
        f"{others}\n"
        "\n"
        "Grammar from this lesson:\n"
        f"{notes}\n"
    )
