import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from teacherlang.speech_cache import SpeechCache
from teacherlang.speech_openai import SpeechError
from teacherlang.speech_player import IDLE, LOADING, PLAYING, SpeechPlayer
from teacherlang.speech_settings import SpeechSettings

SETTINGS = SpeechSettings(api_key="sk-test", voice="marin")


class FakeProcess:
    def __init__(self, path: Path):
        self.path = path
        self.exit_code = None
        self.terminated = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = -15

    def wait(self, timeout=None):
        return self.exit_code

    def kill(self):
        self.exit_code = -9


class FakeSynthesizer:
    """Blocks each request until the test releases it, so LOADING can be observed."""

    def __init__(self, outcome=b"audio"):
        self.outcome = outcome
        self.calls = []
        self.release = threading.Event()

    def __call__(self, text, api_key, voice):
        self.calls.append((text, api_key, voice))
        self.release.wait(timeout=5)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class SpeechPlayerTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.cache = SpeechCache(Path(self._dir.name))
        self.synthesizer = FakeSynthesizer()
        self.processes: list[FakeProcess] = []
        self.player = SpeechPlayer(self.cache, self.synthesizer, self._start)

    def tearDown(self):
        self.synthesizer.release.set()
        self._dir.cleanup()

    def _start(self, path):
        process = FakeProcess(path)
        self.processes.append(process)
        return process

    def _poll_until(self, state):
        deadline = time.monotonic() + 5
        errors = []
        while time.monotonic() < deadline:
            error = self.player.poll()
            if error is not None:
                errors.append(error)
            if self.player.state == state:
                return errors
            time.sleep(0.01)
        self.fail(f"state stayed {self.player.state}, expected {state}")

    def test_fetch_then_play_then_idle(self):
        self.player.play("Hello.", SETTINGS)
        self.assertEqual(self.player.state, LOADING)
        self.synthesizer.release.set()
        self.assertEqual(self._poll_until(PLAYING), [])
        self.assertEqual(self.synthesizer.calls, [("Hello.", "sk-test", "marin")])
        self.assertEqual(self.processes[0].path.read_bytes(), b"audio")

        self.processes[0].exit_code = 0
        self.assertIsNone(self.player.poll())
        self.assertEqual(self.player.state, IDLE)

    def test_cached_audio_plays_without_fetching(self):
        path = self.cache.put("Hello.", "marin", b"saved")
        self.player.play("Hello.", SETTINGS)
        self.assertEqual(self.player.state, PLAYING)
        self.assertEqual(self.processes[0].path, path)
        self.assertEqual(self.synthesizer.calls, [])

    def test_result_of_a_stopped_request_is_dropped(self):
        self.player.play("Hello.", SETTINGS)
        self.player.stop()
        self.synthesizer.release.set()
        deadline = time.monotonic() + 5
        while self.player._results.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNone(self.player.poll())
        self.assertEqual(self.player.state, IDLE)
        self.assertEqual(self.processes, [])

    def test_replaced_request_plays_only_the_new_sentence(self):
        self.player.play("First.", SETTINGS)
        self.player.play("Second.", SETTINGS)
        self.synthesizer.release.set()
        self._poll_until(PLAYING)
        time.sleep(0.05)  # Give the first fetch time to report too.
        self.player.poll()
        self.assertEqual(len(self.processes), 1)
        self.assertEqual(self.processes[0].path, self.cache.get("Second.", "marin"))

    def test_stop_terminates_playback(self):
        self.cache.put("Hello.", "marin", b"saved")
        self.player.play("Hello.", SETTINGS)
        self.player.stop()
        self.assertTrue(self.processes[0].terminated)
        self.assertEqual(self.player.state, IDLE)
        self.assertIsNone(self.player.poll())

    def test_stop_kills_a_process_that_ignores_terminate(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("afplay", 1), -9]
        player = SpeechPlayer(self.cache, self.synthesizer, lambda _path: process)
        self.cache.put("Hello.", "marin", b"saved")
        player.play("Hello.", SETTINGS)
        player.stop()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_fetch_error_is_reported_once(self):
        self.synthesizer.outcome = SpeechError("OpenAI API 키가 올바르지 않습니다.")
        self.synthesizer.release.set()
        self.player.play("Hello.", SETTINGS)
        self.assertEqual(self._poll_until(IDLE), ["OpenAI API 키가 올바르지 않습니다."])
        self.assertIsNone(self.player.poll())

    def test_unexpected_fetch_error_is_reported(self):
        self.synthesizer.outcome = ValueError("boom")
        self.synthesizer.release.set()
        self.player.play("Hello.", SETTINGS)
        self.assertEqual(self._poll_until(IDLE), ["음성을 만들지 못했습니다. (ValueError)"])

    def test_playback_failures_are_reported(self):
        self.cache.put("Hello.", "marin", b"saved")
        self.player.play("Hello.", SETTINGS)
        self.processes[0].exit_code = 1
        self.assertEqual(self.player.poll(), "음성을 재생하지 못했습니다.")

        def missing_player(_path):
            raise FileNotFoundError("afplay")

        player = SpeechPlayer(self.cache, self.synthesizer, missing_player)
        player.play("Hello.", SETTINGS)
        self.assertEqual(player.state, IDLE)
        self.assertIn("음성을 재생하지 못했습니다.", player.poll())


if __name__ == "__main__":
    unittest.main()
