"""Runtime settings, overridable through environment variables."""

import os
from dataclasses import dataclass, replace
from pathlib import Path

from .model_settings import ModelSettings, load_model_settings
from .storage_settings import clamp_retention_days, load_storage_settings

# Set on the tutor's own `claude -p` process so the hook never tutors itself.
RECURSION_GUARD_ENV = "ENGTEACHER_ACTIVE"
MODEL_SETTINGS_FILE = "model.json"
STORAGE_SETTINGS_FILE = "storage.json"


def _default_home() -> Path:
    state_root = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_root) / "engteacher"


@dataclass(frozen=True)
class Config:
    home: Path
    provider: str
    model: str
    claude_bin: str
    codex_bin: str
    tutor_timeout_sec: float
    context_messages: int
    context_chars_per_message: int
    max_prompt_chars: int
    retention_days: int

    @property
    def lessons_path(self) -> Path:
        return self.home / "lessons.jsonl"

    @property
    def model_settings_path(self) -> Path:
        return self.home / MODEL_SETTINGS_FILE

    @property
    def storage_settings_path(self) -> Path:
        return self.home / STORAGE_SETTINGS_FILE

    @property
    def gui_settings_path(self) -> Path:
        return self.home / "gui.json"

    @property
    def notes_path(self) -> Path:
        return self.home / "notes.json"

    @property
    def error_log_path(self) -> Path:
        return self.home / "errors.log"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _resolve_model_settings(home: Path) -> ModelSettings:
    """ENGTEACHER_MODEL wins over the model saved from the GUI, which wins over the default."""
    settings = load_model_settings(home / MODEL_SETTINGS_FILE)
    env_model = os.environ.get("ENGTEACHER_MODEL")
    return replace(settings, model=env_model) if env_model else settings


def _resolve_retention_days(home: Path) -> int:
    """ENGTEACHER_RETENTION_DAYS wins over the value saved from the GUI, then the default."""
    try:
        return clamp_retention_days(int(os.environ["ENGTEACHER_RETENTION_DAYS"]))
    except (KeyError, ValueError):
        return load_storage_settings(home / STORAGE_SETTINGS_FILE).retention_days


def load_config() -> Config:
    home = Path(os.environ.get("ENGTEACHER_HOME") or _default_home())
    model_settings = _resolve_model_settings(home)
    return Config(
        home=home,
        provider=model_settings.provider,
        model=model_settings.model,
        claude_bin=os.environ.get("ENGTEACHER_CLAUDE_BIN", "claude"),
        codex_bin=os.environ.get("ENGTEACHER_CODEX_BIN", "codex"),
        tutor_timeout_sec=float(_int_env("ENGTEACHER_TIMEOUT_SEC", 90)),
        context_messages=_int_env("ENGTEACHER_CONTEXT_MESSAGES", 6),
        context_chars_per_message=_int_env("ENGTEACHER_CONTEXT_CHARS", 600),
        max_prompt_chars=_int_env("ENGTEACHER_MAX_PROMPT_CHARS", 2000),
        retention_days=_resolve_retention_days(home),
    )
