"""Builds a macOS TeacherLang.app whose own bundle name and icon show in the Dock.

The Dock label comes from the bundle that holds the running executable, so the
app carries a private copy of the interpreter stub instead of using Python.app.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .install import REPO_ROOT

APP_NAME = "TeacherLang"
BUNDLE_ID = "local.teacherlang.gui"
LAUNCHER_NAME = "launch"
INTERPRETER_NAME = APP_NAME  # The process name shown by the OS is this file name.
ICON_SOURCE = REPO_ROOT / "teacherlang" / "assets" / "icon.icns"
ICON_FILE_NAME = "icon.icns"
INFO_PLIST_PATH = Path("Contents") / "Info.plist"
LAUNCHER_PATH = Path("Contents") / "MacOS" / LAUNCHER_NAME
INTERPRETER_PATH = Path("Contents") / "MacOS" / INTERPRETER_NAME
ICON_PATH = Path("Contents") / "Resources" / ICON_FILE_NAME
CODESIGN_TIMEOUT_SEC = 30


class AppBundleError(RuntimeError):
    pass


def framework_interpreter_stub() -> Path:
    """The framework build's Python.app executable; other builds have no such stub."""
    stub = Path(sys.base_prefix) / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if not stub.is_file():
        raise AppBundleError(
            f"{stub} not found; run with a framework Python (e.g. Homebrew python3)"
        )
    return stub


def render_info_plist() -> bytes:
    return plistlib.dumps({
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": LAUNCHER_NAME,
        "CFBundleIconFile": ICON_FILE_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleVersion": "1.0",
        "CFBundleShortVersionString": "1.0",
        "NSHighResolutionCapable": True,
    })


def render_launcher(source_root: Path) -> str:
    # exec keeps the process inside this bundle, which is what names the Dock entry.
    return (
        "#!/bin/sh\n"
        'DIR=$(cd "$(dirname "$0")" && pwd)\n'
        f'PYTHONPATH={_shell_quote(str(source_root))} exec "$DIR/{INTERPRETER_NAME}" '
        '-m teacherlang.gui "$@"\n'
    )


def text_files(source_root: Path) -> dict[Path, str]:
    """Generated files keyed by bundle-relative path; used to preview changes to an old bundle."""
    return {
        INFO_PLIST_PATH: render_info_plist().decode("utf-8"),
        LAUNCHER_PATH: render_launcher(source_root),
    }


def read_existing_text_files(app_path: Path) -> dict[Path, str]:
    existing: dict[Path, str] = {}
    for relative in text_files(REPO_ROOT):
        try:
            existing[relative] = (app_path / relative).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            existing[relative] = ""
    return existing


def is_teacherlang_bundle(app_path: Path) -> bool:
    try:
        with (app_path / INFO_PLIST_PATH).open("rb") as handle:
            return plistlib.load(handle).get("CFBundleIdentifier") == BUNDLE_ID
    except (OSError, plistlib.InvalidFileException):
        return False


def build_app(app_path: Path, source_root: Path, interpreter_stub: Path) -> None:
    """Assembles the bundle in a sibling temp dir, then swaps it in for `app_path`."""
    if app_path.exists() and not is_teacherlang_bundle(app_path):
        raise AppBundleError(f"{app_path} exists and is not a TeacherLang app; not touching it")
    app_path.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".teacherlang-app-", dir=app_path.parent))
    try:
        staged = staging_root / app_path.name
        _assemble(staged, source_root, interpreter_stub)
        if app_path.exists():
            shutil.rmtree(app_path)  # Verified above to be a TeacherLang bundle.
        staged.rename(app_path)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _assemble(staged: Path, source_root: Path, interpreter_stub: Path) -> None:
    for relative, text in text_files(source_root).items():
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (staged / LAUNCHER_PATH).chmod(0o755)
    interpreter = staged / INTERPRETER_PATH
    shutil.copy2(interpreter_stub, interpreter)
    _sign_ad_hoc(interpreter)
    icon = staged / ICON_PATH
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ICON_SOURCE, icon)


def _sign_ad_hoc(executable: Path) -> None:
    # The stub's signature was bound to Python.app's Info.plist; arm64 kills it once moved.
    try:
        completed = subprocess.run(
            ["codesign", "--force", "--sign", "-", str(executable)],
            capture_output=True, text=True, timeout=CODESIGN_TIMEOUT_SEC)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AppBundleError(f"codesign failed: {exc}") from exc
    if completed.returncode != 0:
        raise AppBundleError(f"codesign failed: {completed.stderr.strip()}")


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
