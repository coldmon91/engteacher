"""Append-only JSONL lesson log shared by the hook (writer) and the viewer (reader)."""

import fcntl
import json
import os
from datetime import date, datetime
from pathlib import Path

from .archive import log_lock, rotate_daily

_FILE_MODE = 0o600  # Lessons contain the user's raw prompts.


def append_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        # Several sessions may finish at once; the lock keeps each line intact.
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(text.rstrip("\n") + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def append_lesson(path: Path, record: dict, retention_days: int) -> None:
    """Appends the record, first archiving the log if it holds a past day."""
    with log_lock(path):
        try:
            rotate_daily(path, date.today(), retention_days)
        finally:
            # A failed rotation must not lose the lesson; its error still propagates.
            append_line(path, json.dumps(record, ensure_ascii=False))


def append_error(path: Path, message: str) -> None:
    append_line(path, f"{datetime.now().isoformat(timespec='seconds')} {message}")


def parse_lesson_line(line: str) -> dict | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None
