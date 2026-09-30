"""Builds TeacherLang.app so the Dock shows "TeacherLang" instead of "Python".

Shows what an existing app would lose and asks before replacing it.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from .app_bundle import (
    APP_NAME,
    AppBundleError,
    build_app,
    framework_interpreter_stub,
    is_teacherlang_bundle,
    read_existing_text_files,
    text_files,
)
from .install import REPO_ROOT

DEFAULT_APP_PATH = Path.home() / "Applications" / f"{APP_NAME}.app"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="teacherlang-make-app", description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_APP_PATH, help="app bundle path")
    parser.add_argument("--dry-run", action="store_true", help="show the diff without writing")
    parser.add_argument("-y", "--yes", action="store_true", help="replace without asking")
    return parser.parse_args(argv)


def _diff_against_existing(app_path: Path) -> str:
    existing = read_existing_text_files(app_path)
    chunks = []
    for relative, new_text in text_files(REPO_ROOT).items():
        chunks.extend(difflib.unified_diff(
            existing[relative].splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile=f"a/{relative}", tofile=f"b/{relative}"))
    return "".join(chunks)


def _confirm_replace(app_path: Path, assume_yes: bool) -> bool:
    diff = _diff_against_existing(app_path)
    print(f"{app_path} exists and will be replaced entirely (interpreter copy included).")
    print(diff if diff else "Info.plist and launcher are unchanged.")
    if assume_yes:
        return True
    return input("Replace? [y/N] ").strip().lower() == "y"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if sys.platform != "darwin":
        print("teacherlang-make-app: macOS only", file=sys.stderr)
        return 1
    try:
        stub = framework_interpreter_stub()
        if args.out.exists():
            if not is_teacherlang_bundle(args.out):
                raise AppBundleError(f"{args.out} exists and is not a TeacherLang app")
            if args.dry_run:
                _confirm_replace(args.out, assume_yes=True)
                return 0
            if not _confirm_replace(args.out, args.yes):
                print("Aborted.")
                return 1
        elif args.dry_run:
            print(f"Would create {args.out}")
            return 0
        build_app(args.out, REPO_ROOT, stub)
    except AppBundleError as exc:
        print(f"teacherlang-make-app: {exc}", file=sys.stderr)
        return 1
    print(f"Built {args.out}")
    print(f"Launch: open '{args.out}'  (rebuild after a Homebrew Python upgrade or moving this checkout)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
