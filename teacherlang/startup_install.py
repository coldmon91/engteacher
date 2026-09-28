"""Offers to register the hook when the viewer or the GUI starts and finds it missing.

Only a missing entry counts: an entry with a different Python or path may be deliberate.
Nothing here stops the caller from starting; failures and refusals only print a notice.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .install import (
    DEFAULT_SETTINGS,
    INSTALL_SCRIPT,
    InstallError,
    build_install_command,
    commit_settings,
    read_settings,
    render_diff,
    serialize_settings,
)
from .settings_patch import SettingsShapeError, apply_hook, is_hook_registered

SKIP_FLAG = "--no-install-check"
SKIP_FLAG_HELP = "do not offer to install the Claude Code hook when it is missing"
RESTART_NOTICE = "Restart running Claude Code sessions to make sure they pick up the change."


@dataclass(frozen=True)
class PendingInstall:
    path: Path
    old_text: str
    new_text: str

    @property
    def diff(self) -> str:
        return render_diff(self.old_text, self.new_text, self.path)


def find_pending_install(settings_path: Path = DEFAULT_SETTINGS) -> PendingInstall | None:
    """Returns the change that would register the hook, or None when it is already registered."""
    path = settings_path.expanduser()
    old_text, settings = read_settings(path)
    if is_hook_registered(settings):
        return None
    # Same interpreter the bin/ launchers pick, so the hook runs where this program runs.
    command = build_install_command(os.environ.get("TEACHERLANG_PYTHON"))
    try:
        patched, _ = apply_hook(settings, command)
    except SettingsShapeError as exc:
        raise InstallError(f"{path}: {exc}") from exc
    return PendingInstall(path, old_text, serialize_settings(patched))


def apply_pending_install(pending: PendingInstall) -> Path | None:
    """Writes the change; returns the backup path, or None when settings.json was new."""
    return commit_settings(pending.path, pending.old_text, pending.new_text)


def _can_prompt_on_terminal() -> bool:
    # A background job reading the terminal would be stopped by SIGTTIN.
    try:
        return sys.stdin.isatty() and os.tcgetpgrp(sys.stdin.fileno()) == os.getpgrp()
    except OSError:
        return False


def _ask_yes(question: str) -> bool:
    try:
        return input(question).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def offer_install_in_terminal(settings_path: Path = DEFAULT_SETTINGS) -> None:
    try:
        pending = find_pending_install(settings_path)
        if pending is None:
            return
        if not _can_prompt_on_terminal():
            print(f"teacherlang: Claude Code hook is not installed; run {INSTALL_SCRIPT}",
                  file=sys.stderr)
            return
        print(pending.diff)
        if not _ask_yes("\nClaude Code hook is not installed. Install it now? [y/N] "):
            print(f"Skipped; install later with {INSTALL_SCRIPT}\n")
            return
        backup = apply_pending_install(pending)
    except (InstallError, OSError) as exc:
        print(f"teacherlang: hook install skipped: {exc}", file=sys.stderr)
        return
    if backup:
        print(f"Backup: {backup}")
    print(f"Hook added in {pending.path}.\n{RESTART_NOTICE}\n")
