import tempfile
import unittest
from pathlib import Path

from engteacher.card_browser import ALL_MODE, NOTES_MODE, CardBrowser
from engteacher.notes import NoteStore


def _record(n: int) -> dict:
    return {"time": f"2026-09-28T13:0{n}:00+09:00", "session_id": "s1", "original": f"text {n}"}


class CardBrowserTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "notes.json"
        self.browser = CardBrowser(NoteStore(self.path))
        self.browser.add_lessons([_record(1), _record(2), _record(3)])

    def tearDown(self):
        self._dir.cleanup()

    def _save(self, *numbers: int) -> None:
        store = NoteStore(self.path)
        for n in numbers:
            store.save(_record(n))

    def test_toggle_saved_in_all_mode(self):
        self.assertTrue(self.browser.can_save())
        self.browser.toggle_saved()
        self.assertTrue(self.browser.is_current_saved())
        self.browser.toggle_saved()
        self.assertFalse(self.browser.is_current_saved())

    def test_notes_mode_shows_saved_cards_in_time_order(self):
        self._save(3, 1)
        self.assertTrue(self.browser.set_mode(NOTES_MODE))
        self.assertEqual(len(self.browser.deck), 2)
        self.assertEqual(self.browser.current(), _record(3))
        self.browser.deck.older()
        self.assertEqual(self.browser.current(), _record(1))

    def test_modes_keep_their_own_position(self):
        self._save(1, 2)
        self.browser.deck.older()
        self.browser.deck.older()
        self.browser.toggle_mode()
        self.browser.deck.older()
        self.browser.toggle_mode()
        self.assertEqual(self.browser.mode, ALL_MODE)
        self.assertEqual(self.browser.current(), _record(1))
        self.browser.toggle_mode()
        self.assertEqual(self.browser.current(), _record(1))

    def test_new_lessons_leave_notes_mode_alone(self):
        self._save(1)
        self.browser.set_mode(NOTES_MODE)
        self.assertFalse(self.browser.add_lessons([_record(4)]))
        self.assertEqual(len(self.browser.deck), 1)
        self.browser.set_mode(ALL_MODE)
        self.assertEqual(self.browser.current(), _record(4))

    def test_unsaved_note_stays_until_next_switch(self):
        self._save(1, 2)
        self.browser.set_mode(NOTES_MODE)
        self.browser.toggle_saved()
        self.assertEqual(self.browser.current(), _record(2))
        self.assertFalse(self.browser.is_current_saved())
        self.assertEqual(len(self.browser.deck), 2)
        self.browser.toggle_saved()  # Saving it again is still possible.
        self.assertTrue(self.browser.is_current_saved())
        self.browser.toggle_saved()

        self.browser.toggle_mode()
        self.browser.toggle_mode()
        self.assertEqual(len(self.browser.deck), 1)
        self.assertEqual(self.browser.current(), _record(1))

    def test_empty_notes_mode(self):
        self.browser.set_mode(NOTES_MODE)
        self.assertIsNone(self.browser.current())
        self.assertFalse(self.browser.can_save())

    def test_unreadable_notes_disable_saving_until_reload_succeeds(self):
        self._save(3)
        self.path.write_text("{broken", encoding="utf-8")
        self.browser.toggle_saved()
        self.assertIsNotNone(self.browser.notes_error)
        self.assertFalse(self.browser.can_save())
        self.assertFalse(self.browser.is_current_saved())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

        self.browser.set_mode(NOTES_MODE)
        self.assertIsNone(self.browser.current())
        self.assertIsNotNone(self.browser.notes_error)

        self.path.write_text('{"notes": []}', encoding="utf-8")
        self.browser.set_mode(ALL_MODE)
        self.assertIsNone(self.browser.notes_error)
        self.assertTrue(self.browser.can_save())

    def test_unreadable_notes_at_start(self):
        self.path.write_text("{broken", encoding="utf-8")
        browser = CardBrowser(NoteStore(self.path))
        browser.add_lessons([_record(1)])
        self.assertIsNotNone(browser.notes_error)
        self.assertFalse(browser.can_save())

    def test_unknown_mode_is_ignored(self):
        self.assertFalse(self.browser.set_mode("other"))
        self.assertFalse(self.browser.set_mode(ALL_MODE))


if __name__ == "__main__":
    unittest.main()
