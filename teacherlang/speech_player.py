"""Plays one sentence at a time: fetches its audio off the main thread, then runs afplay.

Tk-free; the GUI calls `poll()` on its own timer to move the state forward.
"""

import queue
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from . import speech_openai
from .speech_cache import SpeechCache
from .speech_openai import SpeechError
from .speech_settings import SpeechSettings

IDLE = "idle"
LOADING = "loading"
PLAYING = "playing"
PLAYER_COMMAND = "afplay"
STOP_WAIT_SEC = 1.0

Synthesize = Callable[[str, str, str], bytes]


def playback_available() -> bool:
    return shutil.which(PLAYER_COMMAND) is not None


def start_afplay(path: Path) -> subprocess.Popen:
    return subprocess.Popen([PLAYER_COMMAND, str(path)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class SpeechPlayer:
    """State machine IDLE -> (LOADING ->) PLAYING -> IDLE; all methods run on one thread.

    Fetch threads share only `_results`, a thread-safe queue. Every play or stop bumps the
    request id, so a result that arrives after its request was replaced is dropped.
    """

    def __init__(self, cache: SpeechCache, synthesize: Synthesize = speech_openai.synthesize,
                 start_playback: Callable[[Path], subprocess.Popen] = start_afplay):
        self._cache = cache
        self._synthesize = synthesize
        self._start_playback = start_playback
        self._results: queue.Queue = queue.Queue()
        self._request_id = 0
        self._state = IDLE
        self._process: subprocess.Popen | None = None
        self._error: str | None = None

    @property
    def state(self) -> str:
        return self._state

    def play(self, text: str, settings: SpeechSettings) -> None:
        """Replaces whatever is playing; a failure is reported by the next `poll()`."""
        self.stop()
        cached = self._cache.get(text, settings.voice)
        if cached is not None:
            self._start(cached)
            return
        self._state = LOADING
        threading.Thread(target=self._fetch, daemon=True,
                         args=(self._request_id, text, settings.api_key, settings.voice)).start()

    def stop(self) -> None:
        self._request_id += 1
        self._state = IDLE
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=STOP_WAIT_SEC)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=STOP_WAIT_SEC)

    def poll(self) -> str | None:
        """Advances the state; returns the error message of a failed request, if any."""
        self._take_results()
        if self._state == PLAYING and self._process is not None:
            exit_code = self._process.poll()
            if exit_code is not None:
                self._process = None
                self._state = IDLE
                if exit_code != 0:
                    self._fail("음성을 재생하지 못했습니다.")
        error, self._error = self._error, None
        return error

    def _fetch(self, request_id: int, text: str, api_key: str, voice: str) -> None:
        try:
            outcome: bytes | SpeechError = self._synthesize(text, api_key, voice)
        except SpeechError as error:
            outcome = error
        except Exception as error:  # A fetch thread must always report back.
            outcome = SpeechError(f"음성을 만들지 못했습니다. ({type(error).__name__})")
        self._results.put((request_id, text, voice, outcome))

    def _take_results(self) -> None:
        while True:
            try:
                request_id, text, voice, outcome = self._results.get_nowait()
            except queue.Empty:
                return
            if request_id != self._request_id:
                continue  # Replaced or stopped while fetching.
            if isinstance(outcome, SpeechError):
                self._fail(str(outcome))
                continue
            try:
                path = self._cache.put(text, voice, outcome)
            except OSError as error:
                self._fail(f"음성 파일을 저장하지 못했습니다. ({error})")
                continue
            self._start(path)

    def _start(self, path: Path) -> None:
        try:
            self._process = self._start_playback(path)
        except OSError as error:
            self._fail(f"음성을 재생하지 못했습니다. ({error})")
            return
        self._state = PLAYING

    def _fail(self, message: str) -> None:
        self._state = IDLE
        self._error = message
