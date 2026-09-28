"""UserPromptSubmit hook entry point: tutor the typed prompt and log the lesson.

Registered as an async hook, so it never delays or alters the Claude Code session.
It prints nothing and always exits 0; failures go to the error log.
"""

import json
import os
import sys
from datetime import datetime

from . import tutor
from .config import RECURSION_GUARD_ENV, Config, load_config
from .input_filter import select_tutor_input
from .store import append_error, append_lesson
from .transcript import recent_turns

MAX_STDIN_BYTES = 4 * 1024 * 1024


def handle_event(event: dict, config: Config, request_lesson=tutor.request_lesson) -> dict | None:
    """Returns the logged lesson record, or None when the prompt was skipped."""
    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return None
    tutor_input = select_tutor_input(prompt, config.max_prompt_chars)
    if tutor_input is None:
        return None

    context = recent_turns(
        event.get("transcript_path"),
        max_turns=config.context_messages,
        max_chars_per_turn=config.context_chars_per_message,
        exclude_text=prompt,
    )
    lesson = request_lesson(tutor_input, context, config)
    record = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": event.get("session_id"),
        "cwd": event.get("cwd"),
        "language": tutor_input.language,
        "original": tutor_input.text,
        "lesson": lesson,
    }
    append_lesson(config.lessons_path, record)
    return record


def main() -> int:
    if os.environ.get(RECURSION_GUARD_ENV):
        return 0
    config = load_config()
    try:
        event = json.loads(sys.stdin.buffer.read(MAX_STDIN_BYTES))
        if isinstance(event, dict):
            handle_event(event, config)
    except Exception as exc:  # The hook must never break the user's session.
        try:
            append_error(config.error_log_path, f"{type(exc).__name__}: {exc}")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
