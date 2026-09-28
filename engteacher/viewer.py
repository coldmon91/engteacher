"""Terminal viewer that shows lessons as the hook logs them.

Run it in a separate terminal pane: python3 -m engteacher.viewer
"""

import argparse
import os
import sys
import time

from .config import load_config
from .follow import LessonFollower
from .render import Style, render_lesson


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="engteacher-view", description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--history", type=int, default=5, help="lessons to show at start")
    parser.add_argument("--no-follow", action="store_true", help="print history and exit")
    parser.add_argument("--interval", type=float, default=0.5, help="poll interval in seconds")
    return parser.parse_args(argv)


def _print_lessons(lessons: list[dict], style: Style) -> None:
    for record in lessons:
        print(render_lesson(record, style), end="\n\n", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config()
    style = Style(enabled=sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
    follower = LessonFollower(config.lessons_path)

    _print_lessons(follower.history(args.history), style)
    if args.no_follow:
        return 0

    print(style.dim(f"watching {config.lessons_path} (Ctrl-C to quit)"), end="\n\n", flush=True)
    try:
        while True:
            _print_lessons(follower.poll(), style)
            time.sleep(max(0.1, args.interval))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
