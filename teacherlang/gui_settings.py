"""Persistent GUI preferences stored as a small JSON file next to the lesson log."""

from dataclasses import asdict, dataclass
from pathlib import Path

from .settings_file import read_json_object, write_json_atomic

FONT_SIZE_MIN = 9
FONT_SIZE_MAX = 32


@dataclass(frozen=True)
class GuiSettings:
    always_on_top: bool = False
    font_size: int = 14


def clamp_font_size(size: int) -> int:
    return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, size))


def load_gui_settings(path: Path) -> GuiSettings:
    """Returns saved settings; a missing or malformed value falls back to its default."""
    data = read_json_object(path)
    defaults = GuiSettings()
    always_on_top = data.get("always_on_top")
    font_size = data.get("font_size")
    return GuiSettings(
        always_on_top=always_on_top if isinstance(always_on_top, bool) else defaults.always_on_top,
        # bool is an int subclass; reject it so `true` is not read as size 1.
        font_size=clamp_font_size(font_size)
        if isinstance(font_size, int) and not isinstance(font_size, bool)
        else defaults.font_size,
    )


def save_gui_settings(path: Path, settings: GuiSettings) -> None:
    write_json_atomic(path, asdict(settings))
