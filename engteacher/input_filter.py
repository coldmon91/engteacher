"""Decides whether a submitted prompt is the user's own prose worth tutoring."""

import re
from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "ko"]

_FENCED_CODE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
# Characters and shapes that mark a backtick span as code rather than a quoted sentence.
_CODE_HINT = re.compile(r"[(){}\[\]<>=;$\\|/_*#@&^+]|\w\.\w|(?:^|\s)-")
# Pasted content, system reminders and similar tagged blocks are not user prose.
# Claude Code repeats attributes on the closing tag, e.g. </pasted_content id="ab12">.
_TAGGED_BLOCK = re.compile(r"<([A-Za-z][\w-]*)[^>]*>.*?</\1(?:\s[^>]*)?>", re.DOTALL)
_URL = re.compile(r"https?://\S+")
_MENTION_OR_PATH = re.compile(r"(?<!\S)(?:@|~/|\./|/)[\w./-]*[\w/]")
_HANGUL_SYLLABLE = re.compile(r"[가-힣]")
_LATIN_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Claude Code input prefixes: slash command, bash mode.
_COMMAND_PREFIXES = ("/", "!")

MIN_ENGLISH_WORDS = 3
MIN_HANGUL_SYLLABLES = 4


@dataclass(frozen=True)
class TutorInput:
    text: str
    language: Language


def _looks_like_prose(text: str) -> bool:
    if _CODE_HINT.search(text):
        return False
    english_words = sum(1 for token in text.split() if _LATIN_WORD.search(token))
    return (len(_HANGUL_SYLLABLE.findall(text)) >= MIN_HANGUL_SYLLABLES
            or english_words >= MIN_ENGLISH_WORDS)


def _unwrap_prose_span(match: re.Match[str]) -> str:
    """Keeps a backtick-quoted sentence as prose; drops identifiers, paths and commands."""
    content = match.group(1)
    return content if _looks_like_prose(content) else " "


def strip_non_prose(prompt: str) -> str:
    text = _FENCED_CODE.sub(" ", prompt)
    text = _TAGGED_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(_unwrap_prose_span, text)
    text = _URL.sub(" ", text)
    text = _MENTION_OR_PATH.sub(" ", text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line).strip()


def detect_language(text: str) -> Language | None:
    hangul_count = len(_HANGUL_SYLLABLE.findall(text))
    english_words = _LATIN_WORD.findall(text)
    if hangul_count >= MIN_HANGUL_SYLLABLES:
        return "ko"
    if hangul_count == 0 and len(english_words) >= MIN_ENGLISH_WORDS:
        return "en"
    return None


def select_tutor_input(prompt: str, max_chars: int) -> TutorInput | None:
    """Returns the prose to tutor, or None when the prompt should be skipped."""
    if not prompt or prompt.lstrip().startswith(_COMMAND_PREFIXES):
        return None
    text = strip_non_prose(prompt)
    # Very long input is almost always pasted material, not the user's writing.
    if not text or len(text) > max_chars:
        return None
    language = detect_language(text)
    if language is None:
        return None
    return TutorInput(text=text, language=language)
