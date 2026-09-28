"""Incremental reader of the lesson log, like `tail -f` for JSONL records."""

import os
from pathlib import Path

from .store import parse_lesson_line

HISTORY_READ_BYTES = 256 * 1024


class LessonFollower:
    def __init__(self, path: Path):
        self._path = path
        self._position = 0
        self._inode: int | None = None
        self._partial = b""

    def history(self, limit: int) -> list[dict]:
        """Returns the latest `limit` lessons and moves the read position to the end."""
        try:
            with self._path.open("rb") as f:
                stat = os.fstat(f.fileno())
                start = max(0, stat.st_size - HISTORY_READ_BYTES)
                f.seek(start)
                data = f.read()
                self._position = f.tell()
                self._inode = stat.st_ino
        except FileNotFoundError:
            return []

        lines = data.split(b"\n")
        # The last element is an unterminated line (or empty); keep it for the next poll.
        self._partial = lines.pop()
        if start > 0 and lines:
            lines.pop(0)  # Cut in the middle by the offset.
        lessons = self._parse(lines)
        return lessons[-limit:] if limit > 0 else []

    def poll(self) -> list[dict]:
        """Returns lessons appended since the previous call."""
        try:
            stat = self._path.stat()
        except FileNotFoundError:
            return []
        if stat.st_ino != self._inode or stat.st_size < self._position:
            # The log was rotated or truncated; start over from its beginning.
            self._position, self._partial, self._inode = 0, b"", stat.st_ino
        if stat.st_size == self._position:
            return []

        with self._path.open("rb") as f:
            f.seek(self._position)
            data = f.read()
            self._position = f.tell()

        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        return self._parse(lines)

    @staticmethod
    def _parse(lines: list[bytes]) -> list[dict]:
        lessons = []
        for raw in lines:
            record = parse_lesson_line(raw.decode("utf-8", errors="replace"))
            if record is not None:
                lessons.append(record)
        return lessons
