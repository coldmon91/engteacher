#!/usr/bin/env python3
"""Checks, tests, and builds TeacherLang.app from this checkout.

Run it with the Python the app should use; the app copies that interpreter's stub.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)
SOURCE_DIRS = ("teacherlang", "tests")
TEST_TIMEOUT_SEC = 600


class BuildError(RuntimeError):
    pass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build.py", description=__doc__.splitlines()[0])
    parser.add_argument("--skip-tests", action="store_true", help="skip the unit tests")
    parser.add_argument("--skip-app", action="store_true", help="skip building TeacherLang.app")
    parser.add_argument("--out", type=Path, help="app bundle path (default: ~/Applications/TeacherLang.app)")
    parser.add_argument("--dry-run", action="store_true", help="show the app diff without writing")
    parser.add_argument("-y", "--yes", action="store_true", help="replace an existing app without asking")
    return parser.parse_args(argv)


def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        found = ".".join(map(str, sys.version_info[:3]))
        required = ".".join(map(str, MIN_PYTHON))
        raise BuildError(f"Python {required}+ required, running {found} ({sys.executable})")


def check_syntax() -> int:
    """Compiles every source file in memory so no .pyc files are written."""
    paths = [Path(__file__).resolve()]
    for directory in SOURCE_DIRS:
        paths.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    errors = []
    for path in paths:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            errors.append(f"{path.relative_to(REPO_ROOT)}: {exc}")
    if errors:
        raise BuildError("syntax check failed:\n  " + "\n  ".join(errors))
    return len(paths)


def run_tests() -> None:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, timeout=TEST_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills the child on timeout before re-raising.
        raise BuildError(f"tests timed out after {TEST_TIMEOUT_SEC}s") from exc
    if completed.returncode != 0:
        raise BuildError(f"tests failed (exit {completed.returncode})")


def build_app(args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        raise BuildError("TeacherLang.app needs macOS; use --skip-app elsewhere")
    from teacherlang import make_app  # Imported after the version check.

    make_app_argv = []
    if args.out is not None:
        make_app_argv += ["--out", str(args.out)]
    if args.dry_run:
        make_app_argv.append("--dry-run")
    if args.yes:
        make_app_argv.append("--yes")
    if make_app.main(make_app_argv) != 0:
        raise BuildError("app build failed")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        _step("Python version", check_python_version)
        print(f"  {sys.executable} {sys.version.split()[0]}")
        file_count = _step("Syntax check", check_syntax)
        print(f"  {file_count} files OK")
        if not args.skip_tests:
            _step("Unit tests", run_tests)
        if not args.skip_app:
            _step("TeacherLang.app", lambda: build_app(args))
    except BuildError as exc:
        print(f"build.py: {exc}", file=sys.stderr)
        return 1
    print("\nBuild finished.")
    return 0


def _step(title: str, action):
    print(f"\n== {title}", flush=True)
    return action()


if __name__ == "__main__":
    sys.exit(main())
