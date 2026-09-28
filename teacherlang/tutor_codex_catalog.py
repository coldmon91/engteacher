"""Builds a one-model codex catalog that turns off the tools no config flag can remove.

codex takes the tool set of a model from its model catalog (`tool_mode`, `multi_agent_version`,
...). The entry is copied from codex's own models cache, so the model keeps its real limits and
instructions template; only the tool-related fields change.
"""

import os
from pathlib import Path

from .settings_file import read_json_object, write_json_atomic

CATALOG_FILE = "codex-model-catalog.json"
MODELS_CACHE_FILE = "models_cache.json"

# "direct" drops the code-mode `exec`/`wait` tools; the rest drop multi-agent, apply_patch,
# clock and tool search.
_TOOL_FREE_FIELDS = {"tool_mode": "direct", "experimental_supported_tools": [],
                     "supports_search_tool": False}
_TOOL_FIELDS_TO_DROP = ("multi_agent_version", "apply_patch_tool_type")


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _cached_model_entry(model: str) -> dict | None:
    models = read_json_object(_codex_home() / MODELS_CACHE_FILE).get("models")
    if not isinstance(models, list):
        return None
    return next((m for m in models if isinstance(m, dict) and m.get("slug") == model), None)


def write_tool_free_catalog(model: str, home: Path) -> Path | None:
    """Writes the catalog and returns its path; None when codex has not cached `model`."""
    entry = _cached_model_entry(model)
    if entry is None:
        return None
    patched = {key: value for key, value in entry.items() if key not in _TOOL_FIELDS_TO_DROP}
    path = home / CATALOG_FILE
    # Rewritten on every call so a refreshed codex cache is picked up.
    write_json_atomic(path, {"models": [{**patched, **_TOOL_FREE_FIELDS}]})
    return path
