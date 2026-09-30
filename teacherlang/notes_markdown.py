"""Formats saved notes as a Markdown document for reading in an external editor."""

import re
from datetime import datetime
from itertools import groupby

from .render import (DETAIL, FIELD, HEADER, HEADLINE, ITEM, SECTION, Block, Span, lesson_blocks,
                     project_name)

TITLE = "TeacherLang 노트"
UNKNOWN_DATE = "날짜 없음"
UNKNOWN_CLOCK = "--:--"
# Span tag -> Markdown delimiter; untagged and color-only spans stay plain.
TAG_MARKUP = {"bold": "**", "green": "**", "red": "~~"}
# Only the characters that can start emphasis or HTML, so the raw file stays readable.
# Backticks pass through: lessons use them for inline code, and a lone one renders as itself.
_INLINE_SPECIALS = re.compile(r"([\\*_~<])")
_ORDERED_LIST_START = re.compile(r"\d+(?=[.)])")
_LINE_BREAKS = re.compile(r"[\r\n]+")


def notes_markdown(notes: list[dict], exported_at: datetime) -> str:
    """Renders the notes in time order, grouped by day, with every section of each card."""
    ordered = sorted(notes, key=lambda note: str(note.get("time") or ""))
    lines = [f"# {TITLE}", "", f"내보낸 시각: {exported_at:%Y-%m-%d %H:%M} · 노트 {len(ordered)}개"]
    for day, day_notes in groupby(ordered, key=lambda note: _time_parts(note)[0]):
        lines += ["", f"## {day}"]
        for note in day_notes:
            lines += ["", *_card_lines(note)]
    return "\n".join(lines) + "\n"


def _time_parts(record: dict) -> tuple[str, str]:
    """(date, HH:MM) of the lesson; placeholders when its time is missing or malformed."""
    try:
        moment = datetime.fromisoformat(str(record.get("time")))
    except ValueError:
        return UNKNOWN_DATE, UNKNOWN_CLOCK
    return moment.date().isoformat(), moment.strftime("%H:%M")


def _card_lines(record: dict) -> list[str]:
    blocks = [block for block in lesson_blocks(record, show_alternatives=True)
              if block.kind != HEADER]
    headline = next((block for block in blocks if block.kind == HEADLINE), None)
    title = [_time_parts(record)[1], _escape_inline(project_name(record))]
    if headline is not None:
        # Plain text: a heading is already bold, so the headline's color tag adds nothing.
        title.append(_escape_inline("".join(span.text for span in headline.spans)))
    lines = [f"### {' · '.join(title)}", ""]
    for block in blocks:
        if block.kind != HEADLINE:
            lines += _block_lines(block)
    return lines


def _block_lines(block: Block) -> list[str]:
    if block.kind == FIELD:
        return [f"- {block.label}: {_spans_markdown(block.spans, at_line_start=False)}"]
    if block.kind == SECTION:
        return ["", f"#### {block.label}", ""]
    if block.kind == ITEM:
        return [f"- {_spans_markdown(block.spans, at_line_start=True)}"]
    if block.kind == DETAIL:
        return [f"  - {_spans_markdown(block.spans, at_line_start=True)}"]
    return []


def _spans_markdown(spans: list[Span], at_line_start: bool) -> str:
    """`at_line_start` guards text that Markdown would read as a heading, quote, or list."""
    parts = []
    for index, span in enumerate(spans):
        text = _escape_inline(_LINE_BREAKS.sub(" ", span.text))
        if index == 0 and at_line_start and span.tag not in TAG_MARKUP:
            text = _escape_line_start(text)
        parts.append(_marked(text, TAG_MARKUP.get(span.tag)))
    return "".join(parts)


def _marked(text: str, delimiter: str | None) -> str:
    """Keeps surrounding spaces outside the delimiters, where Markdown requires them."""
    core = text.strip()
    if delimiter is None or not core:
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f"{lead}{delimiter}{core}{delimiter}{trail}"


def _escape_inline(text: str) -> str:
    return _INLINE_SPECIALS.sub(r"\\\1", text)


def _escape_line_start(text: str) -> str:
    ordered = _ORDERED_LIST_START.match(text)
    if ordered:
        return f"{text[:ordered.end()]}\\{text[ordered.end():]}"
    if text[:1] in ("#", ">", "-", "+"):
        return f"\\{text}"
    return text
