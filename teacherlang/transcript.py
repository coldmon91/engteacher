"""Extracts recent conversation turns from a Claude Code transcript (JSONL)."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Transcripts can grow to many MB; only the tail is needed for recent turns.
TAIL_READ_BYTES = 512 * 1024

# User records that are harness output rather than typed text.
_HARNESS_PREFIXES = ("<command-", "<local-command", "<system-reminder", "<bash-", "Caveat:")


@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "assistant"
    text: str


def _read_tail_lines(path: Path, max_bytes: int) -> list[str]:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - max_bytes)
        f.seek(start)
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    # The first line is likely cut in the middle when reading from an offset.
    return lines[1:] if start > 0 else lines


def _user_text(content: object) -> str | None:
    # List content on user records holds tool results, not typed text.
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text or text.startswith(_HARNESS_PREFIXES):
        return None
    return text


def _assistant_text(content: object) -> str | None:
    if not isinstance(content, list):
        return None
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def _parse_turn(line: str) -> Turn | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta"):
        return None
    role = record.get("type")
    message = record.get("message")
    if role not in ("user", "assistant") or not isinstance(message, dict):
        return None
    content = message.get("content")
    text = _user_text(content) if role == "user" else _assistant_text(content)
    return Turn(role=role, text=text) if text else None


def _shorten(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def recent_turns(
    transcript_path: str | None,
    max_turns: int,
    max_chars_per_turn: int,
    exclude_text: str | None = None,
    clean_text: Callable[[str], str] | None = None,
) -> list[Turn]:
    """Returns up to `max_turns` latest turns, oldest first; empty on any read failure.

    `clean_text` runs before truncation; a turn it empties is dropped.
    """
    if not transcript_path or max_turns <= 0:
        return []
    path = Path(transcript_path)
    try:
        lines = _read_tail_lines(path, TAIL_READ_BYTES)
    except OSError:
        return []

    turns = [turn for turn in map(_parse_turn, lines) if turn is not None]
    # The prompt being tutored may already be recorded; it is not context for itself.
    if exclude_text and turns and turns[-1].role == "user" and turns[-1].text == exclude_text.strip():
        turns.pop()
    # Newest first, so only kept turns are cleaned and no placeholder label goes to a dropped one.
    selected: list[Turn] = []
    for turn in reversed(turns):
        text = clean_text(turn.text) if clean_text else turn.text
        if text:
            selected.append(Turn(role=turn.role, text=_shorten(text, max_chars_per_turn)))
            if len(selected) == max_turns:
                break
    return selected[::-1]
