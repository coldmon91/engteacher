"""Incremental reader of the lesson log, like `tail -f` for JSONL records.

History also reaches into the compressed archives of past days.
"""

import os
from pathlib import Path
from typing import BinaryIO

from .archive import list_archives, read_archive_lines
from .store import parse_lesson_line

HISTORY_READ_BYTES = 256 * 1024


class LessonFollower:
    def __init__(self, path: Path):
        self._path = path
        self._file: BinaryIO | None = None
        self._partial = b""

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self._partial = b""

    def history(self, limit: int) -> list[dict]:
        """Returns the latest `limit` lessons and moves the read position to the end."""
        self.close()
        lessons, read_whole_log = self._open_at_tail()
        if limit <= 0:
            return []
        if read_whole_log:
            for archive in reversed(list_archives(self._path)):
                if len(lessons) >= limit:
                    break
                lessons = self._parse(read_archive_lines(archive.path)) + lessons
        return lessons[-limit:]

    def poll(self) -> list[dict]:
        """Returns lessons appended since the previous call."""
        lessons = []
        if self._file is not None and not self._is_current():
            # Rotated away: the open handle still reaches what was written before the rotation.
            lessons += self._read_new() + self._parse([self._partial])
            self.close()
        if self._file is None:
            try:
                self._file = self._path.open("rb")
            except FileNotFoundError:
                return lessons
        elif os.fstat(self._file.fileno()).st_size < self._file.tell():
            # Truncated in place; start over from its beginning.
            self._file.seek(0)
            self._partial = b""
        return lessons + self._read_new()

    def _open_at_tail(self) -> tuple[list[dict], bool]:
        """Opens the log and parses its last HISTORY_READ_BYTES; also says if that was all of it."""
        try:
            self._file = self._path.open("rb")
        except FileNotFoundError:
            return [], True
        start = max(0, os.fstat(self._file.fileno()).st_size - HISTORY_READ_BYTES)
        self._file.seek(start)
        lines = self._file.read().split(b"\n")
        # The last element is an unterminated line (or empty); keep it for the next poll.
        self._partial = lines.pop()
        if start > 0 and lines:
            lines.pop(0)  # Cut in the middle by the offset.
        return self._parse(lines), start == 0

    def _is_current(self) -> bool:
        try:
            path_stat = self._path.stat()
        except FileNotFoundError:
            return False
        file_stat = os.fstat(self._file.fileno())
        return (path_stat.st_dev, path_stat.st_ino) == (file_stat.st_dev, file_stat.st_ino)

    def _read_new(self) -> list[dict]:
        data = self._file.read()
        if not data:
            return []
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
