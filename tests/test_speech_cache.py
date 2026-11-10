import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from teacherlang.speech_cache import SpeechCache


class SpeechCacheTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.directory = Path(self._dir.name) / "speech-cache"
        self.cache = SpeechCache(self.directory)

    def tearDown(self):
        self._dir.cleanup()

    def test_put_then_get(self):
        self.assertIsNone(self.cache.get("Hello.", "marin"))
        path = self.cache.put("Hello.", "marin", b"audio")
        self.assertEqual(self.cache.get("Hello.", "marin"), path)
        self.assertEqual(path.read_bytes(), b"audio")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(list(self.directory.iterdir()), [path])  # No temp file left.

    def test_voice_and_text_are_part_of_the_key(self):
        marin = self.cache.put("Hello.", "marin", b"a")
        self.assertNotEqual(self.cache.put("Hello.", "cedar", b"b"), marin)
        self.assertNotEqual(self.cache.put("Hello!", "marin", b"c"), marin)
        self.assertEqual(marin.read_bytes(), b"a")

    def test_get_marks_audio_as_used(self):
        path = self.cache.put("Hello.", "marin", b"audio")
        old = time.time() - 40 * 86400
        os.utime(path, (old, old))
        self.cache.get("Hello.", "marin")
        self.assertGreater(path.stat().st_mtime, old + 86400)

    def test_prune_deletes_only_old_audio(self):
        old = self.cache.put("Old.", "marin", b"o")
        fresh = self.cache.put("Fresh.", "marin", b"f")
        other = self.directory / "notes.txt"
        other.write_text("keep")
        stale = time.time() - 31 * 86400
        for path in (old, other):
            os.utime(path, (stale, stale))
        self.cache.prune(max_age_days=30)
        self.assertEqual(sorted(self.directory.iterdir()), sorted([fresh, other]))

    def test_prune_without_directory_is_quiet(self):
        self.cache.prune()
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
