"""Tutor backend that runs Claude Code headless (`claude -p`)."""

import json

from .config import Config
from .prompts import LESSON_SCHEMA_JSON, SYSTEM_PROMPT
from .tutor_error import TutorError


def build_command(config: Config) -> list[str]:
    # --restricted skips user/project settings (hooks, plugins) and code-running tools;
    # together with the empty tool list the model can only return text.
    # Thinking is off: it multiplied latency and cost by ~6 with no visible quality gain.
    return [
        config.claude_bin,
        "-p",
        "--model", config.model,
        "--effort", "low",
        "--settings", '{"alwaysThinkingEnabled":false}',
        "--restricted",
        "--strict-mcp-config",
        "--tools", "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt", SYSTEM_PROMPT,
        "--output-format", "json",
        "--json-schema", LESSON_SCHEMA_JSON,
    ]


def extract_lesson(stdout: str) -> object:
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TutorError(f"claude output is not JSON: {stdout[:200]!r}") from exc
    if not isinstance(envelope, dict) or envelope.get("is_error"):
        raise TutorError(f"claude reported an error: {str(envelope)[:300]}")
    return envelope.get("structured_output")
