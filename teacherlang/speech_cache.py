"""Generated speech kept on disk, so replaying a sentence costs no API call."""

import hashlib
import os
import tempfile
import time
from pathlib import Path

from .speech_openai import INSTRUCTIONS, MODEL

MAX_AGE_DAYS = 30
_SUFFIX = ".mp3"


class SpeechCache:
    def __init__(self, directory: Path):
        self._directory = directory

    def get(self, text: str, voice: str) -> Path | None:
        """Returns the saved audio and marks it as used, so pruning keeps it.

        Audio that cannot be touched reads as missing; it is fetched and written again.
        """
        path = self._path_for(text, voice)
        try:
            os.utime(path)
        except OSError:
            return None
        return path

    def put(self, text: str, voice: str, audio: bytes) -> Path:
        """Writes atomically; mkstemp makes the file 0600, as the sentence is user text."""
        path = self._path_for(text, voice)
        self._directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._directory, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(audio)
            os.replace(tmp_name, path)
        except BaseException:
            os.unlink(tmp_name)
            raise
        return path

    def prune(self, max_age_days: int = MAX_AGE_DAYS) -> None:
        """Deletes audio unused for `max_age_days`; files that vanish or resist are skipped."""
        cutoff = time.time() - max_age_days * 86400
        try:
            entries = list(os.scandir(self._directory))
        except OSError:
            return
        for entry in entries:
            if not entry.name.endswith(_SUFFIX):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    os.unlink(entry.path)
            except OSError:
                continue

    def _path_for(self, text: str, voice: str) -> Path:
        # Every input that changes the audio is part of the key.
        key = "\0".join((MODEL, voice, INSTRUCTIONS, text)).encode("utf-8")
        return self._directory / f"{hashlib.sha256(key).hexdigest()}{_SUFFIX}"
