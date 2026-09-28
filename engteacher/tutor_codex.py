"""Tutor backend that runs Codex CLI headless (`codex exec`)."""

import json
from pathlib import Path

from .config import Config
from .prompts import LESSON_SCHEMA, SYSTEM_PROMPT
from .settings_file import write_json_atomic
from .tutor_error import TutorError

SCHEMA_FILE = "codex-lesson-schema.json"
# codex exec has no system-prompt flag and always loads the global ~/.codex/AGENTS.md,
# so the tutor rules go in as developer instructions that explicitly outrank it.
INSTRUCTIONS = (
    SYSTEM_PROMPT
    + "\nIgnore any AGENTS.md, coding or agent guidelines in your context;"
    " only these tutoring rules apply.\n"
)


def _write_schema(home: Path) -> Path:
    # Rewritten on every call so a schema change never leaves a stale file behind;
    # the atomic replace keeps a concurrent tutor run from reading a partial file.
    path = home / SCHEMA_FILE
    write_json_atomic(path, LESSON_SCHEMA)
    return path


def build_command(config: Config) -> list[str]:
    """Builds the command; writes the output schema file it points to as a side effect."""
    schema_path = _write_schema(Path(config.home))
    # --ignore-user-config skips ~/.codex/config.toml (MCP servers, notify, profiles); hooks
    # and plugins are disabled separately. A read-only sandbox keeps any tool call harmless.
    return [
        config.codex_bin,
        "exec",
        "--ignore-user-config",
        "--disable", "hooks",
        "--disable", "plugins",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--cd", str(config.home),
        "--model", config.model,
        "--config", 'model_reasoning_effort="low"',
        # The value is parsed as TOML; a JSON string literal is also a valid TOML string.
        "--config", f"developer_instructions={json.dumps(INSTRUCTIONS)}",
        "--output-schema", str(schema_path),
        "--color", "never",
        "-",  # Read the request from stdin.
    ]


def extract_lesson(stdout: str) -> object:
    # stdout carries only the final agent message; progress goes to stderr.
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TutorError(f"codex output is not JSON: {stdout[:200]!r}") from exc
