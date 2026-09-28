"""Registers (or with --uninstall, removes) the teacherlang hook in Claude Code user settings.

Shows a diff and asks before writing; keeps a timestamped backup of the old file.
Runs on any Python 3 so it can report a too-old interpreter instead of crashing.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .config import load_config
from .settings_patch import (
    PatchResult,
    SettingsShapeError,
    apply_hook,
    build_hook_command,
    remove_hook,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO_ROOT / "bin" / "teacherlang-hook"
VIEWER_SCRIPT = REPO_ROOT / "bin" / "teacherlang-view"
INSTALL_SCRIPT = REPO_ROOT / "bin" / "teacherlang-install"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
MIN_PYTHON = (3, 10)
DIFF_LINE_MAX_CHARS = 160  # Some existing hook commands are several KB long.


class InstallError(RuntimeError):
    pass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="teacherlang-install", description=__doc__.splitlines()[0])
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS, help="settings.json path")
    parser.add_argument("--python", help=f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ for the hook")
    parser.add_argument("--dry-run", action="store_true", help="show the diff without writing")
    parser.add_argument("-y", "--yes", action="store_true", help="apply without asking")
    parser.add_argument("--uninstall", action="store_true", help="remove the hook instead")
    return parser.parse_args(argv)


def resolve_python(explicit: str | None) -> str:
    candidate = explicit or shutil.which("python3")
    if not candidate:
        raise InstallError("python3 not found on PATH; pass --python")
    check = f"import sys; sys.exit(0 if sys.version_info >= {MIN_PYTHON} else 1)"
    try:
        completed = subprocess.run([candidate, "-c", check], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError(f"cannot run {candidate}: {exc}") from exc
    if completed.returncode != 0:
        raise InstallError(
            f"{candidate} is older than Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}; pass --python"
        )
    return candidate


def read_settings(path: Path) -> tuple[str, dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", {}
    try:
        settings = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InstallError(f"{path} is not valid JSON ({exc}); fix it first") from exc
    if not isinstance(settings, dict):
        raise InstallError(f"{path} does not hold a JSON object")
    return text, settings


def serialize_settings(settings: dict) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def render_diff(old_text: str, new_text: str, path: Path) -> str:
    diff = difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(), f"{path} (current)", f"{path} (new)", lineterm=""
    )
    return "\n".join(
        line if len(line) <= DIFF_LINE_MAX_CHARS else line[:DIFF_LINE_MAX_CHARS] + " …"
        for line in diff
    )


def backup_settings(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.teacherlang-backup-{stamp}")
    # Runs within the same second must not overwrite an earlier backup.
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.teacherlang-backup-{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def commit_settings(path: Path, old_text: str, new_text: str) -> Path | None:
    """Backs up and replaces settings.json; returns the backup path, or None for a new file."""
    # Claude Code may rewrite settings.json itself; never overwrite a change made meanwhile.
    if read_settings(path)[0] != old_text:
        raise InstallError(f"{path} changed while waiting; rerun the installer")
    backup = backup_settings(path) if old_text else None
    write_atomically(path, new_text)
    return backup


def build_install_command(explicit_python: str | None) -> str:
    if not os.access(HOOK_SCRIPT, os.X_OK):
        raise InstallError(f"{HOOK_SCRIPT} is missing or not executable")
    return build_hook_command(resolve_python(explicit_python), str(HOOK_SCRIPT))


def _confirm(assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise InstallError("not an interactive terminal; rerun with --yes to apply")
    return input("Apply this change? [y/N] ").strip().lower() in ("y", "yes")


def _write_change(path: Path, old_text: str, patched: dict, args: argparse.Namespace) -> bool:
    """Shows the diff, confirms, backs up and writes; returns True when the file was written."""
    new_text = serialize_settings(patched)
    print(render_diff(old_text, new_text, path))
    if args.dry_run:
        print(f"\nDry run: {path} not written.")
        return False
    if not _confirm(args.yes):
        print("Aborted; nothing written.")
        return False

    backup = commit_settings(path, old_text, new_text)
    if backup:
        print(f"\nBackup: {backup}")
    return True


def install(args: argparse.Namespace) -> int:
    command = build_install_command(args.python)

    path: Path = args.settings.expanduser()
    old_text, settings = read_settings(path)
    try:
        patched, result = apply_hook(settings, command)
    except SettingsShapeError as exc:
        raise InstallError(f"{path}: {exc}") from exc

    if result is PatchResult.UNCHANGED:
        print(f"Already installed in {path}; nothing to change.")
        return 0
    if not _write_change(path, old_text, patched, args):
        return 0 if args.dry_run else 1

    print(f"Hook {result.value} in {path}.")
    print("Restart running Claude Code sessions to make sure they pick up the change.")
    print(f"Watch lessons in another pane: {VIEWER_SCRIPT}")
    return 0


def uninstall(args: argparse.Namespace) -> int:
    path: Path = args.settings.expanduser()
    old_text, settings = read_settings(path)
    patched, result = remove_hook(settings)

    if result is PatchResult.NOT_FOUND:
        print(f"No teacherlang hook in {path}; nothing to change.")
        return 0
    if not _write_change(path, old_text, patched, args):
        return 0 if args.dry_run else 1

    print(f"Hook removed from {path}.")
    print("Restart running Claude Code sessions to make sure they pick up the change.")
    print(f"Lesson history is kept in {load_config().home}; delete it manually if unwanted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        return uninstall(args) if args.uninstall else install(args)
    except InstallError as exc:
        sys.stdout.flush()  # Keep the diff above the error when stdout is not a TTY.
        print(f"teacherlang-install: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
