"""Formats a lesson record as styled text spans, shared by the terminal and GUI viewers."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# Style tag -> ANSI SGR code. The GUI viewer defines a look for each of these tags.
ANSI_CODES = {
    "dim": "2",
    "bold": "1",
    "red": "31",
    "green": "32",
    "cyan": "36",
    "yellow": "33",
}


class Span(NamedTuple):
    text: str
    tag: str | None = None


Line = list[Span]


@dataclass(frozen=True)
class Style:
    enabled: bool

    def apply(self, tag: str | None, text: str) -> str:
        if not self.enabled or tag is None:
            return text
        return f"\033[{ANSI_CODES[tag]}m{text}\033[0m"

    def dim(self, text: str) -> str:
        return self.apply("dim", text)


LABEL_WIDTH = 6
ITEM_PREFIX = "    · "
DETAIL_PREFIX = "      "
# Older lessons list translation steps as issues; they repeat 원문 -> 개선, so they are hidden.
HIDDEN_ISSUE_CATEGORIES = frozenset({"translation"})

# Block kinds: what a line means, so each view can lay it out its own way.
HEADER = "header"
HEADLINE = "headline"
FIELD = "field"
SECTION = "section"
ITEM = "item"
DETAIL = "detail"


class Block(NamedTuple):
    """One logical line of a lesson, without the indentation or bullets a view adds."""

    kind: str
    spans: Line
    # The field name for FIELD, the section name for SECTION; empty otherwise.
    label: str = ""


def _items(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _header(record: dict) -> Block:
    try:
        clock = datetime.fromisoformat(str(record.get("time"))).strftime("%H:%M:%S")
    except ValueError:
        clock = "--:--:--"
    project = Path(str(record.get("cwd") or "")).name or "-"
    return Block(HEADER, [Span(f"{clock} · {project}", "dim")])


def _headline(record: dict, lesson: dict) -> Block:
    if record.get("language") == "ko":
        return Block(HEADLINE, [Span("🌐 번역", "cyan")])
    if lesson.get("needs_fix"):
        return Block(HEADLINE, [Span("✎ 교정", "yellow")])
    return Block(HEADLINE, [Span("✓ 자연스러운 문장", "green")])


def _lesson(record: dict) -> dict:
    return record.get("lesson") if isinstance(record.get("lesson"), dict) else {}


def _alternatives(lesson: dict) -> list[dict]:
    return _items(lesson.get("alternatives"))


def has_alternatives(record: dict) -> bool:
    return bool(_alternatives(_lesson(record)))


def lesson_blocks(record: dict, show_alternatives: bool = False) -> list[Block]:
    """Breaks a lesson into logical lines; tolerates malformed lesson fields.

    `show_alternatives=True` adds the 대안 section last; it is hidden unless a view asks for it.
    """
    lesson = _lesson(record)
    original = str(record.get("original", ""))
    improved = str(lesson.get("improved", ""))
    blocks = [_header(record), _headline(record, lesson), Block(FIELD, [Span(original)], "원문")]
    if improved and improved != original:
        blocks.append(Block(FIELD, [Span(improved, "bold")], "개선"))

    issues = [
        issue
        for issue in _items(lesson.get("issues"))
        if issue.get("category") not in HIDDEN_ISSUE_CATEGORIES
    ]
    if issues:
        blocks.append(Block(SECTION, [], "변경"))
        for issue in issues:
            blocks.append(Block(ITEM, [
                Span(f"[{issue.get('category', '')}]", "dim"),
                Span(" "),
                Span(str(issue.get("before", "")), "red"),
                Span(" → "),
                Span(str(issue.get("after", "")), "green"),
            ]))
            blocks.append(Block(DETAIL, [Span(str(issue.get("explanation_ko", "")))]))

    vocabulary = _items(lesson.get("vocabulary"))
    if vocabulary:
        blocks.append(Block(SECTION, [], "어휘"))
        blocks.extend(
            Block(ITEM, [
                Span(str(v.get("term", "")), "bold"),
                Span(" "),
                Span(str(v.get("ipa", "")), "cyan"),
                Span(" "),
                Span(f"— {v.get('note_ko', '')}", "dim"),
            ])
            for v in vocabulary
        )

    examples = _strings(lesson.get("examples"))
    if examples:
        blocks.append(Block(SECTION, [], "예문"))
        blocks.extend(Block(ITEM, [Span(example)]) for example in examples)

    alternatives = _alternatives(lesson) if show_alternatives else []
    if alternatives:
        blocks.append(Block(SECTION, [], "대안"))
        blocks.extend(
            Block(ITEM, [Span(f"{alt.get('text', '')} "), Span(f"— {alt.get('nuance_ko', '')}", "dim")])
            for alt in alternatives
        )
    return blocks


def _prefixed(prefix: str, spans: Line) -> Line:
    """Joins the prefix into a leading plain span, so plain text stays a single span."""
    if spans and spans[0].tag is None:
        return [Span(prefix + spans[0].text), *spans[1:]]
    return [Span(prefix), *spans]


def _block_line(block: Block, header_rule: bool) -> Line:
    if block.kind == HEADER and header_rule:
        title = f"── {''.join(span.text for span in block.spans)} "
        return [Span(title + "─" * max(0, 48 - len(title)), "dim")]
    if block.kind == FIELD:
        return [Span("  "), Span(block.label.ljust(LABEL_WIDTH), "dim"), *block.spans]
    if block.kind == SECTION:
        return [Span("  "), Span(block.label, "dim")]
    if block.kind == ITEM:
        return _prefixed(ITEM_PREFIX, block.spans)
    if block.kind == DETAIL:
        return _prefixed(DETAIL_PREFIX, block.spans)
    return block.spans


def lesson_lines(record: dict, header_rule: bool = True,
                 show_alternatives: bool = False) -> list[Line]:
    """Lays out a lesson as indented lines of styled spans for text views.

    `header_rule=False` drops the separator rule for views that frame each lesson themselves.
    """
    return [_block_line(block, header_rule)
            for block in lesson_blocks(record, show_alternatives=show_alternatives)]


def render_lesson(record: dict, style: Style) -> str:
    return "\n".join(
        "".join(style.apply(span.tag, span.text) for span in line) for line in lesson_lines(record)
    )
