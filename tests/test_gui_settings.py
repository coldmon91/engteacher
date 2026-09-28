import argparse
import json
import tempfile
import unittest
from pathlib import Path

from teacherlang.gui import _startup_settings
from teacherlang.gui_settings import (
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    GuiSettings,
    load_gui_settings,
    save_gui_settings,
)


class GuiSettingsStoreTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "state" / "gui.json"

    def tearDown(self):
        self._dir.cleanup()

    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_gui_settings(self.path), GuiSettings())

    def test_round_trip_creates_directory(self):
        settings = GuiSettings(always_on_top=True, font_size=18)
        save_gui_settings(self.path, settings)
        self.assertEqual(load_gui_settings(self.path), settings)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])  # No temp file left.

    def test_malformed_values_fall_back_per_field(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"always_on_top": "yes", "font_size": 99}), encoding="utf-8")
        self.assertEqual(load_gui_settings(self.path), GuiSettings(font_size=FONT_SIZE_MAX))

        self.path.write_text(json.dumps({"always_on_top": True, "font_size": True}), encoding="utf-8")
        self.assertEqual(load_gui_settings(self.path), GuiSettings(always_on_top=True))

    def test_invalid_json_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{not json", "[1, 2]"):
            self.path.write_text(content, encoding="utf-8")
            self.assertEqual(load_gui_settings(self.path), GuiSettings())


class StartupSettingsTest(unittest.TestCase):
    def test_options_override_saved_settings(self):
        saved = GuiSettings(always_on_top=False, font_size=20)
        args = argparse.Namespace(topmost=True, font_size=1)
        self.assertEqual(_startup_settings(saved, args),
                         GuiSettings(always_on_top=True, font_size=FONT_SIZE_MIN))

    def test_no_options_keep_saved_settings(self):
        saved = GuiSettings(always_on_top=True, font_size=20)
        args = argparse.Namespace(topmost=False, font_size=None)
        self.assertEqual(_startup_settings(saved, args), saved)


if __name__ == "__main__":
    unittest.main()
