"""Chronological deck of lesson records browsed one card at a time."""


class CardDeck:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._index = -1  # -1 only while the deck is empty.

    def __len__(self) -> int:
        return len(self._records)

    def add(self, records: list[dict]) -> bool:
        """Appends records (oldest first); returns True if the shown card changed.

        The view follows new records only when the newest card is shown,
        so a user reading an older card keeps their place.
        """
        if not records:
            return False
        was_at_newest = self.is_at_newest()
        self._records.extend(records)
        if was_at_newest:
            self._index = len(self._records) - 1
        return was_at_newest

    def current(self) -> dict | None:
        return self._records[self._index] if self._records else None

    def position(self) -> int:
        """1-based position of the shown card; 0 when empty."""
        return self._index + 1

    def is_at_oldest(self) -> bool:
        return self._index <= 0

    def is_at_newest(self) -> bool:
        return self._index == len(self._records) - 1

    def older(self) -> bool:
        return self._move_to(self._index - 1)

    def newer(self) -> bool:
        return self._move_to(self._index + 1)

    def newest(self) -> bool:
        return self._move_to(len(self._records) - 1)

    def _move_to(self, index: int) -> bool:
        """Returns True if the shown card changed."""
        if not 0 <= index < len(self._records) or index == self._index:
            return False
        self._index = index
        return True
