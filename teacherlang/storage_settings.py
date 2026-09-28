"""Lesson log retention, saved by the GUI and read by the hook on every prompt.

storage.json layout:
    {"retention_days": 14}
"""

from dataclasses import asdict, dataclass
from pathlib import Path

from .settings_file import read_json_object, write_json_atomic

RETENTION_DAYS_MIN = 0  # 0 keeps archives forever.
RETENTION_DAYS_MAX = 365
DEFAULT_RETENTION_DAYS = 14


@dataclass(frozen=True)
class StorageSettings:
    retention_days: int = DEFAULT_RETENTION_DAYS


def clamp_retention_days(days: int) -> int:
    return max(RETENTION_DAYS_MIN, min(RETENTION_DAYS_MAX, days))


def load_storage_settings(path: Path) -> StorageSettings:
    """Returns saved settings; a missing or malformed value falls back to its default."""
    days = read_json_object(path).get("retention_days")
    # bool is an int subclass; reject it so `true` is not read as 1 day.
    if isinstance(days, int) and not isinstance(days, bool):
        return StorageSettings(retention_days=clamp_retention_days(days))
    return StorageSettings()


def save_storage_settings(path: Path, settings: StorageSettings) -> None:
    write_json_atomic(path, asdict(settings))
