"""Picks the sentence of a lesson record to read aloud."""

import re

from .input_filter import PLACEHOLDER

_SPACE_BEFORE_PUNCTUATION = re.compile(r" +([,.!?;:])")


def spoken_text(record: dict) -> str:
    """The improved sentence without code placeholders; empty when there is nothing to read.

    The record no longer holds the code a placeholder stood for, so it is dropped.
    """
    lesson = record.get("lesson")
    improved = lesson.get("improved") if isinstance(lesson, dict) else None
    if not isinstance(improved, str):
        return ""
    text = " ".join(PLACEHOLDER.sub(" ", improved).split())
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    # A sentence of placeholders leaves only punctuation, which has nothing to say.
    return text if any(char.isalnum() for char in text) else ""
