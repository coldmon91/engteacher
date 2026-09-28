"""Tutor provider and model choice, saved by the GUI and read by the hook on every prompt.

model.json layout:
    {"provider": "claude", "providers": {"claude": {"model": "haiku"}}}
Each provider keeps its own section, so switching providers never loses another one's model.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .settings_file import read_json_object, write_json_atomic


@dataclass(frozen=True)
class ProviderSpec:
    default_model: str
    model_presets: tuple[str, ...]


# Providers the tutor can run. Adding one (pi) takes an entry here and a backend in tutor.py.
PROVIDERS = {
    # Aliases `claude --model` accepts for the latest model of each family.
    "claude": ProviderSpec(default_model="haiku", model_presets=("haiku", "sonnet", "opus", "fable")),
    # Models listed in ~/.codex/models_cache.json (codex-cli 0.156.0).
    "codex": ProviderSpec(
        default_model="gpt-6-luna",
        model_presets=("gpt-6-luna", "gpt-6-sol", "gpt-6-astra",
                       "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"),
    ),
}
DEFAULT_PROVIDER = "claude"

# Aliases and full model names, e.g. claude-sonnet-5 or claude-opus-5-5[1m]. A leading
# letter or digit keeps a saved value from being read as another CLI flag.
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,99}")


@dataclass(frozen=True)
class ModelSettings:
    provider: str = DEFAULT_PROVIDER
    model: str = PROVIDERS[DEFAULT_PROVIDER].default_model


def is_valid_model(name: str) -> bool:
    return bool(_MODEL_NAME.fullmatch(name))


def _provider_sections(data: dict) -> dict:
    sections = data.get("providers")
    return sections if isinstance(sections, dict) else {}


def load_model_settings(path: Path, provider: str | None = None) -> ModelSettings:
    """Returns the saved choice, or the model saved for `provider` when one is given.

    An unknown provider or an invalid model falls back to the default.
    """
    data = read_json_object(path)
    if provider is None:
        provider = data.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER

    section = _provider_sections(data).get(provider)
    model = section.get("model") if isinstance(section, dict) else None
    if not isinstance(model, str) or not is_valid_model(model):
        model = PROVIDERS[provider].default_model
    return ModelSettings(provider=provider, model=model)


def save_model_settings(path: Path, settings: ModelSettings) -> None:
    """Saves the choice while keeping other providers' sections and unknown keys."""
    if settings.provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {settings.provider!r}")
    if not is_valid_model(settings.model):
        raise ValueError(f"invalid model name: {settings.model!r}")

    data = read_json_object(path)
    sections = _provider_sections(data)
    section = sections.get(settings.provider)
    sections[settings.provider] = {**(section if isinstance(section, dict) else {}),
                                   "model": settings.model}
    write_json_atomic(path, {**data, "provider": settings.provider, "providers": sections})
