import json
import stat
import tempfile
import unittest
from pathlib import Path

from engteacher.notes import NotesError, NoteStore, lesson_key


def _record(n: int) -> dict:
    return {"time": f"2026-09-28T13:0{n}:00+09:00", "session_id": "s1", "original": f"text {n}"}


class NoteStoreTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "state" / "notes.json"
        self.store = NoteStore(self.path)

    def tearDown(self):
        self._dir.cleanup()

    def _write_raw(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def test_missing_file_is_empty(self):
        self.assertEqual(self.store.load(), [])
        self.assertFalse(self.path.exists())

    def test_save_and_remove_round_trip(self):
        self.store.save(_record(1))
        self.assertTrue(self.store.is_saved(_record(1)))
        self.assertEqual(NoteStore(self.path).load(), [_record(1)])

        self.store.remove(_record(1))
        self.assertFalse(self.store.is_saved(_record(1)))
        self.assertEqual(NoteStore(self.path).load(), [])

    def test_saving_twice_keeps_one_copy(self):
        self.store.save(_record(1))
        self.store.save({**_record(1), "lesson": {"improved": "changed"}})
        self.assertEqual(self.store.load(), [_record(1)])

    def test_removing_unsaved_card_does_not_write(self):
        self.store.remove(_record(1))
        self.assertFalse(self.path.exists())

    def test_keeps_notes_added_by_another_window(self):
        other = NoteStore(self.path)
        self.store.save(_record(1))
        other.save(_record(2))
        self.store.save(_record(3))
        self.assertEqual(self.store.load(), [_record(1), _record(2), _record(3)])

    def test_unreadable_file_raises_and_is_left_untouched(self):
        for broken in ("{not json", "[]", '{"notes": {}}', "\udcff"):
            with self.subTest(broken=broken):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_bytes(broken.encode("utf-8", errors="surrogateescape"))
                before = self.path.read_bytes()
                with self.assertRaises(NotesError):
                    self.store.load()
                with self.assertRaises(NotesError):
                    self.store.save(_record(1))
                self.assertEqual(self.path.read_bytes(), before)

    def test_entries_that_are_not_objects_are_preserved(self):
        self._write_raw(json.dumps({"notes": ["stray", _record(1)], "extra": 1}))
        self.assertEqual(self.store.load(), [_record(1)])
        self.store.save(_record(2))
        self.store.remove(_record(1))
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved, {"notes": ["stray", _record(2)], "extra": 1})

    def test_file_is_private(self):
        self.store.save(_record(1))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_key_tolerates_missing_fields(self):
        self.assertEqual(lesson_key({}), ("", "", ""))
        self.assertEqual(lesson_key({"session_id": None}), ("", "", ""))


if __name__ == "__main__":
    unittest.main()
