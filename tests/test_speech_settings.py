import json
import stat
import tempfile
import unittest
from pathlib import Path

from teacherlang.speech_settings import (
    DEFAULT_VOICE,
    SpeechSettings,
    load_speech_settings,
    save_speech_settings,
)


class SpeechSettingsTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "state" / "speech.json"

    def tearDown(self):
        self._dir.cleanup()

    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_speech_settings(self.path),
                         SpeechSettings(api_key="", voice=DEFAULT_VOICE, auto_play=False))

    def test_round_trip_is_private_and_leaves_no_temp_file(self):
        settings = SpeechSettings(api_key="sk-test", voice="cedar", auto_play=True)
        save_speech_settings(self.path, settings)
        self.assertEqual(load_speech_settings(self.path), settings)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_malformed_values_fall_back_per_field(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"api_key": 1, "voice": "robot", "auto_play": "yes"}),
                             encoding="utf-8")
        self.assertEqual(load_speech_settings(self.path), SpeechSettings())

        self.path.write_text(json.dumps({"api_key": " sk-x \n", "voice": "nova"}),
                             encoding="utf-8")
        self.assertEqual(load_speech_settings(self.path),
                         SpeechSettings(api_key="sk-x", voice="nova"))

    def test_invalid_json_gives_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_speech_settings(self.path), SpeechSettings())


if __name__ == "__main__":
    unittest.main()
