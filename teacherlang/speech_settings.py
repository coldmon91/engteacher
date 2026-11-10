"""Speech playback preferences, including the OpenAI API key, stored next to the lesson log."""

from dataclasses import asdict, dataclass
from pathlib import Path

from .settings_file import read_json_object, write_json_atomic

# Voices of gpt-4o-mini-tts, per the OpenAI text-to-speech guide.
VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage",
          "shimmer", "verse", "marin", "cedar")
DEFAULT_VOICE = "marin"


@dataclass(frozen=True)
class SpeechSettings:
    api_key: str = ""
    voice: str = DEFAULT_VOICE
    auto_play: bool = False


def load_speech_settings(path: Path) -> SpeechSettings:
    """Returns saved settings; a missing or malformed value falls back to its default."""
    data = read_json_object(path)
    defaults = SpeechSettings()
    api_key = data.get("api_key")
    voice = data.get("voice")
    auto_play = data.get("auto_play")
    return SpeechSettings(
        api_key=api_key.strip() if isinstance(api_key, str) else defaults.api_key,
        voice=voice if voice in VOICES else defaults.voice,
        auto_play=auto_play if isinstance(auto_play, bool) else defaults.auto_play,
    )


def save_speech_settings(path: Path, settings: SpeechSettings) -> None:
    """The file holds the API key; write_json_atomic replaces it with a 0600 file."""
    write_json_atomic(path, asdict(settings))
