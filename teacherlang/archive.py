"""Daily rotation of the lesson log: past days are gzip-compressed and pruned by age.

Files next to the active log (lessons.jsonl), all mode 0600:
    lessons-2026-09-27.jsonl.gz     archive of one past day
    lessons-2026-09-27.2.jsonl.gz   later archive of the same day (the clock moved back)
    lessons-2026-09-27.jsonl        renamed but not yet compressed (left by a crash)
    lessons.lock                    serializes rotation with appends
"""

import fcntl
import gzip
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

_FILE_MODE = 0o600  # Archives contain the user's raw prompts.
_COMPARE_CHUNK = 64 * 1024


@dataclass(frozen=True, order=True)
class Archive:
    day: date
    sequence: int
    path: Path


@contextmanager
def log_lock(log_path: Path) -> Iterator[None]:
    """Holds an exclusive lock that every writer takes before rotating or appending."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log_path.with_name(f"{log_path.stem}.lock"), os.O_RDWR | os.O_CREAT, _FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # Closing releases the lock.


def rotate_daily(log_path: Path, today: date, retention_days: int) -> None:
    """Archives the log if its last write was before `today`, then prunes old archives.

    The caller must hold `log_lock`. `retention_days` 0 keeps archives forever.
    """
    _compress_pending(log_path)
    log_day = _last_write_day(log_path)
    if log_day is not None and log_day < today:
        # Every append rotates first, so a log last written on a past day holds only that day.
        pending = _pending_path(log_path, log_day)
        os.replace(log_path, pending)
        _compress(log_path, pending, log_day)
    if retention_days > 0:
        _prune(log_path, oldest_kept=today - timedelta(days=retention_days))


def list_archives(log_path: Path) -> list[Archive]:
    """Returns the compressed archives, oldest first."""
    pattern = re.compile(rf"{re.escape(log_path.stem)}-(\d{{4}}-\d{{2}}-\d{{2}})(?:\.(\d+))?"
                         rf"{re.escape(log_path.suffix)}\.gz")
    archives = []
    for match, path in _dated_files(log_path, pattern):
        day = _parse_day(match.group(1))
        if day is not None:
            archives.append(Archive(day, int(match.group(2) or 1), path))
    return sorted(archives)


def read_archive_lines(path: Path) -> list[bytes]:
    """Returns the archive's lines; a truncated or corrupt archive yields what could be read."""
    lines = []
    try:
        with gzip.open(path, "rb") as f:
            for line in f:
                lines.append(line)
    except (OSError, EOFError):  # BadGzipFile is an OSError.
        pass
    return lines


def _dated_files(log_path: Path, pattern: re.Pattern) -> Iterator[tuple[re.Match, Path]]:
    try:
        entries = list(log_path.parent.iterdir())
    except FileNotFoundError:
        return
    for path in entries:
        match = pattern.fullmatch(path.name)
        if match:
            yield match, path


def _parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _last_write_day(log_path: Path) -> date | None:
    try:
        return date.fromtimestamp(log_path.stat().st_mtime)
    except FileNotFoundError:
        return None


def _pending_path(log_path: Path, day: date) -> Path:
    return log_path.with_name(f"{log_path.stem}-{day.isoformat()}{log_path.suffix}")


def _compress_pending(log_path: Path) -> None:
    """Finishes a rotation that a crash interrupted."""
    pattern = re.compile(rf"{re.escape(log_path.stem)}-(\d{{4}}-\d{{2}}-\d{{2}})"
                         rf"{re.escape(log_path.suffix)}")
    for match, pending in _dated_files(log_path, pattern):
        day = _parse_day(match.group(1))
        if day is None:
            continue
        same_day = [a for a in list_archives(log_path) if a.day == day]
        # A crash after the archive was written but before the pending file was removed.
        if same_day and _same_content(same_day[-1].path, pending):
            pending.unlink()
        else:
            _compress(log_path, pending, day)


def _compress(log_path: Path, pending: Path, day: date) -> None:
    """Compresses `pending` into a new archive of `day`, then removes it."""
    sequence = max((a.sequence for a in list_archives(log_path) if a.day == day), default=0) + 1
    suffix = f".{sequence}" if sequence > 1 else ""
    target = log_path.with_name(f"{log_path.stem}-{day.isoformat()}{suffix}{log_path.suffix}.gz")

    # mkstemp creates the file with mode 0600; the rename makes the archive appear whole.
    fd, tmp_name = tempfile.mkstemp(dir=log_path.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "wb") as raw, pending.open("rb") as src:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw) as gz:
                shutil.copyfileobj(src, gz)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        os.unlink(tmp_name)
        raise
    pending.unlink()


def _same_content(archive: Path, plain: Path) -> bool:
    try:
        with gzip.open(archive, "rb") as a, plain.open("rb") as b:
            while True:
                chunk = a.read(_COMPARE_CHUNK)
                if chunk != b.read(_COMPARE_CHUNK):
                    return False
                if not chunk:
                    return True
    except (OSError, EOFError):
        return False


def _prune(log_path: Path, oldest_kept: date) -> None:
    for archive in list_archives(log_path):
        if archive.day < oldest_kept:
            archive.path.unlink(missing_ok=True)
