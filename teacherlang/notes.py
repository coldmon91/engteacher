"""Saved cards ("notes"), kept apart from the lesson log so log pruning never drops them.

notes.json layout:
    {"notes": [<lesson record>, ...]}   full copies, in save order
"""

import json
from collections.abc import Callable
from pathlib import Path

from .archive import log_lock
from .settings_file import write_json_atomic

NoteKey = tuple[str, str, str]


class NotesError(Exception):
    """The notes file exists but cannot be read; it must not be overwritten."""


def lesson_key(record: dict) -> NoteKey:
    """Identifies a lesson; records carry no id, and these three together are unique in practice."""
    return (str(record.get("time") or ""), str(record.get("session_id") or ""),
            str(record.get("original") or ""))


def _is_note(entry: object) -> bool:
    return isinstance(entry, dict)


class NoteStore:
    def __init__(self, path: Path):
        self._path = path
        self._saved_keys: set[NoteKey] = set()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[dict]:
        """Returns the saved records in save order; raises NotesError for an unreadable file."""
        notes = [entry for entry in self._read_document()["notes"] if _is_note(entry)]
        self._saved_keys = {lesson_key(note) for note in notes}
        return notes

    def is_saved(self, record: dict) -> bool:
        """Answers from the last load or change, without touching the file."""
        return lesson_key(record) in self._saved_keys

    def save(self, record: dict) -> None:
        key = lesson_key(record)

        def add(entries: list) -> list | None:
            if any(_is_note(entry) and lesson_key(entry) == key for entry in entries):
                return None
            return [*entries, record]

        self._update(add)

    def remove(self, record: dict) -> None:
        key = lesson_key(record)

        def drop(entries: list) -> list | None:
            kept = [entry for entry in entries if not (_is_note(entry) and lesson_key(entry) == key)]
            return kept if len(kept) != len(entries) else None

        self._update(drop)

    def _update(self, change: Callable[[list], list | None]) -> None:
        """Re-reads the file under a lock, so another window's changes are kept, not overwritten.

        `change` returns the new entry list, or None when there is nothing to write.
        Entries that are not objects are carried over untouched.
        """
        with log_lock(self._path):
            document = self._read_document()
            entries = change(document["notes"])
            if entries is None:
                entries = document["notes"]
            else:
                write_json_atomic(self._path, {**document, "notes": entries})
        self._saved_keys = {lesson_key(entry) for entry in entries if _is_note(entry)}

    def _read_document(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"notes": []}
        except (OSError, ValueError) as error:  # UnicodeDecodeError is a ValueError.
            raise NotesError(str(error)) from error
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
            raise NotesError('expected {"notes": [...]}')
        return data
