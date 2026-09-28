"""Adds or updates the engteacher hook entry in a Claude Code settings dict."""

from __future__ import annotations

import copy
import shlex
from enum import Enum

HOOK_EVENT = "UserPromptSubmit"
HOOK_SCRIPT_NAME = "engteacher-hook"
HOOK_TIMEOUT_SEC = 120


class PatchResult(Enum):
    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    NOT_FOUND = "not found"


class SettingsShapeError(ValueError):
    pass


def build_hook_command(python_path: str, hook_script_path: str) -> str:
    return f"ENGTEACHER_PYTHON={shlex.quote(python_path)} {shlex.quote(hook_script_path)}"


def _build_hook(command: str) -> dict:
    return {"type": "command", "command": command, "timeout": HOOK_TIMEOUT_SEC, "async": True}


def _is_engteacher_hook(hook: object) -> bool:
    return isinstance(hook, dict) and HOOK_SCRIPT_NAME in str(hook.get("command", ""))


def _find_engteacher_hook(groups: list) -> dict | None:
    for group in groups:
        hooks = group.get("hooks") if isinstance(group, dict) else None
        for hook in hooks if isinstance(hooks, list) else []:
            if _is_engteacher_hook(hook):
                return hook
    return None


def _event_groups(settings: dict) -> list:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SettingsShapeError('"hooks" is not an object')
    groups = hooks.setdefault(HOOK_EVENT, [])
    if not isinstance(groups, list):
        raise SettingsShapeError(f'"hooks.{HOOK_EVENT}" is not an array')
    return groups


def apply_hook(settings: dict, command: str) -> tuple[dict, PatchResult]:
    """Returns a patched copy; an existing engteacher entry is updated in place, not duplicated."""
    patched = copy.deepcopy(settings)
    groups = _event_groups(patched)
    desired = _build_hook(command)

    existing = _find_engteacher_hook(groups)
    if existing is None:
        groups.append({"hooks": [desired]})
        return patched, PatchResult.ADDED
    if all(existing.get(key) == value for key, value in desired.items()):
        return settings, PatchResult.UNCHANGED
    existing.update(desired)
    return patched, PatchResult.UPDATED


def remove_hook(settings: dict) -> tuple[dict, PatchResult]:
    """Returns a copy without engteacher entries; containers left empty by the removal go too."""
    hooks = settings.get("hooks")
    groups = hooks.get(HOOK_EVENT) if isinstance(hooks, dict) else None
    if not isinstance(groups, list) or _find_engteacher_hook(groups) is None:
        return settings, PatchResult.NOT_FOUND

    patched = copy.deepcopy(settings)
    kept_groups = []
    for group in patched["hooks"][HOOK_EVENT]:
        group_hooks = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(group_hooks, list):
            kept_groups.append(group)
            continue
        remaining = [hook for hook in group_hooks if not _is_engteacher_hook(hook)]
        # Other hooks sharing the group stay; a group that held only engteacher is dropped.
        if remaining or len(remaining) == len(group_hooks):
            group["hooks"] = remaining
            kept_groups.append(group)

    if kept_groups:
        patched["hooks"][HOOK_EVENT] = kept_groups
    else:
        del patched["hooks"][HOOK_EVENT]
        if not patched["hooks"]:
            del patched["hooks"]
    return patched, PatchResult.REMOVED
