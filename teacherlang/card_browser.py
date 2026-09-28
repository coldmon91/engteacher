"""Switches between every lesson and the saved notes, and saves or unsaves the shown card."""

from .card_deck import CardDeck
from .notes import NotesError, NoteStore, lesson_key

ALL_MODE = "all"
NOTES_MODE = "notes"


class CardBrowser:
    def __init__(self, store: NoteStore):
        self._store = store
        self._all = CardDeck()
        self._notes = CardDeck()
        self._mode = ALL_MODE
        self._notes_error: str | None = None
        self._load_notes()  # Fills the saved state shown in the all mode.

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def deck(self) -> CardDeck:
        """The deck of the current mode; navigation goes through it."""
        return self._notes if self._mode == NOTES_MODE else self._all

    @property
    def notes_error(self) -> str | None:
        """Why the notes file cannot be read; saving stays off until a reload succeeds."""
        return self._notes_error

    def current(self) -> dict | None:
        return self.deck.current()

    def add_lessons(self, records: list[dict]) -> bool:
        """Adds new lessons to the all deck; returns True if the shown card changed."""
        changed = self._all.add(records)
        return changed and self._mode == ALL_MODE

    def set_mode(self, mode: str) -> bool:
        """Returns True if the mode changed. Every switch re-reads the notes file."""
        if mode not in (ALL_MODE, NOTES_MODE) or mode == self._mode:
            return False
        self._mode = mode
        notes = self._load_notes()
        if mode == NOTES_MODE:
            self._rebuild_notes_deck(notes or [])
        return True

    def toggle_mode(self) -> bool:
        return self.set_mode(NOTES_MODE if self._mode == ALL_MODE else ALL_MODE)

    def can_save(self) -> bool:
        return self.current() is not None and self._notes_error is None

    def is_current_saved(self) -> bool:
        """False while the notes file is unreadable, since the saved state is then unknown."""
        record = self.current()
        return record is not None and self._notes_error is None and self._store.is_saved(record)

    def toggle_saved(self) -> None:
        """Saves or unsaves the shown card; an unsaved note stays shown until the next switch.

        A write failure (OSError) propagates; an unreadable file is kept in `notes_error`.
        """
        record = self.current()
        if record is None or self._notes_error is not None:
            return
        try:
            if self._store.is_saved(record):
                self._store.remove(record)
            else:
                self._store.save(record)
        except NotesError as error:
            self._notes_error = str(error)

    def _load_notes(self) -> list[dict] | None:
        try:
            notes = self._store.load()
        except NotesError as error:
            self._notes_error = str(error)
            return None
        self._notes_error = None
        return notes

    def _rebuild_notes_deck(self, notes: list[dict]) -> None:
        """Keeps the note shown before, if it is still saved; otherwise shows the newest."""
        previous = self._notes.current()
        ordered = sorted(notes, key=lambda note: str(note.get("time") or ""))
        self._notes = CardDeck()
        self._notes.add(ordered)
        if previous is None:
            return
        previous_key = lesson_key(previous)
        for index, note in enumerate(ordered):
            if lesson_key(note) == previous_key:
                self._notes.move_to(index)
                return
