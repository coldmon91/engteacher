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
# Older lessons list translation steps as issues; they repeat 원문 -> 개선, so they are hidden.
HIDDEN_ISSUE_CATEGORIES = frozenset({"translation"})


def _items(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _header(record: dict, with_rule: bool) -> Line:
    try:
        clock = datetime.fromisoformat(str(record.get("time"))).strftime("%H:%M:%S")
    except ValueError:
        clock = "--:--:--"
    project = Path(str(record.get("cwd") or "")).name or "-"
    if not with_rule:
        return [Span(f"{clock} · {project}", "dim")]
    title = f"── {clock} · {project} "
    return [Span(title + "─" * max(0, 48 - len(title)), "dim")]


def _headline(record: dict, lesson: dict) -> Line:
    if record.get("language") == "ko":
        return [Span("🌐 번역", "cyan")]
    if lesson.get("needs_fix"):
        return [Span("✎ 교정", "yellow")]
    return [Span("✓ 자연스러운 문장", "green")]


def _field(label: str, *value: Span) -> Line:
    return [Span("  "), Span(label.ljust(LABEL_WIDTH), "dim"), *value]


def _section(label: str) -> Line:
    return [Span("  "), Span(label, "dim")]


def _lesson(record: dict) -> dict:
    return record.get("lesson") if isinstance(record.get("lesson"), dict) else {}


def _alternatives(lesson: dict) -> list[dict]:
    return _items(lesson.get("alternatives"))


def has_alternatives(record: dict) -> bool:
    return bool(_alternatives(_lesson(record)))


def lesson_lines(record: dict, header_rule: bool = True,
                 show_alternatives: bool = False) -> list[Line]:
    """Lays out a lesson as lines of styled spans; tolerates malformed lesson fields.

    `header_rule=False` drops the separator rule for views that frame each lesson themselves.
    `show_alternatives=True` adds the 대안 section, which is hidden unless a view asks for it.
    """
    lesson = _lesson(record)
    original = str(record.get("original", ""))
    improved = str(lesson.get("improved", ""))
    lines = [_header(record, header_rule), _headline(record, lesson), _field("원문", Span(original))]
    if improved and improved != original:
        lines.append(_field("개선", Span(improved, "bold")))

    issues = [
        issue
        for issue in _items(lesson.get("issues"))
        if issue.get("category") not in HIDDEN_ISSUE_CATEGORIES
    ]
    if issues:
        lines.append(_section("변경"))
        for issue in issues:
            lines.append([
                Span("    · "),
                Span(f"[{issue.get('category', '')}]", "dim"),
                Span(" "),
                Span(str(issue.get("before", "")), "red"),
                Span(" → "),
                Span(str(issue.get("after", "")), "green"),
            ])
            lines.append([Span(f"      {issue.get('explanation_ko', '')}")])

    alternatives = _alternatives(lesson) if show_alternatives else []
    if alternatives:
        lines.append(_section("대안"))
        lines.extend(
            [Span(f"    · {alt.get('text', '')} "), Span(f"— {alt.get('nuance_ko', '')}", "dim")]
            for alt in alternatives
        )

    vocabulary = _items(lesson.get("vocabulary"))
    if vocabulary:
        lines.append(_section("어휘"))
        lines.extend(
            [
                Span("    · "),
                Span(str(v.get("term", "")), "bold"),
                Span(" "),
                Span(str(v.get("ipa", "")), "cyan"),
                Span(" "),
                Span(f"— {v.get('note_ko', '')}", "dim"),
            ]
            for v in vocabulary
        )

    examples = _strings(lesson.get("examples"))
    if examples:
        lines.append(_section("예문"))
        lines.extend([Span(f"    · {example}")] for example in examples)
    return lines


def render_lesson(record: dict, style: Style) -> str:
    return "\n".join(
        "".join(style.apply(span.tag, span.text) for span in line) for line in lesson_lines(record)
    )
