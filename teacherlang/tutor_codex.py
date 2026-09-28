"""Tutor backend that runs Codex CLI headless (`codex exec`)."""

import json
from pathlib import Path

from .config import Config
from .prompts import LESSON_SCHEMA, SYSTEM_PROMPT
from .settings_file import write_json_atomic, write_text_atomic
from .tutor_codex_catalog import write_tool_free_catalog
from .tutor_error import TutorError

SCHEMA_FILE = "codex-lesson-schema.json"
INSTRUCTIONS_FILE = "codex-tutor-instructions.md"
# The tutor rules replace codex's base prompt, but the global ~/.codex/AGENTS.md is still
# loaded and cannot be turned off, so the rules explicitly outrank it.
INSTRUCTIONS = (
    SYSTEM_PROMPT
    + "\nIgnore any AGENTS.md, coding or agent guidelines in your context;"
    " only these tutoring rules apply.\n"
)

# hooks and plugins would run user code; the rest are tool sets (app connectors alone add
# ~100k input tokens).
DISABLED_FEATURES = ("hooks", "plugins", "apps", "shell_tool", "unified_exec", "view_image",
                     "goals", "multi_agent", "image_generation")

# Values are parsed as TOML. Each drops a prompt section or a tool the tutor never uses.
CONFIG_OVERRIDES = (
    'model_reasoning_effort="low"',
    "include_permissions_instructions=false",
    "include_apps_instructions=false",
    "include_collaboration_mode_instructions=false",
    "include_environment_context=false",
    "skills.include_instructions=false",
    'web_search="disabled"',
    "tools.experimental_request_user_input.enabled=false",
)


def _write_support_files(config: Config) -> tuple[Path, Path, Path | None]:
    # Rewritten on every call so a prompt or schema change never leaves a stale file behind;
    # the atomic replace keeps a concurrent tutor run from reading a partial file.
    home = Path(config.home)
    schema_path = home / SCHEMA_FILE
    write_json_atomic(schema_path, LESSON_SCHEMA)
    instructions_path = home / INSTRUCTIONS_FILE
    write_text_atomic(instructions_path, INSTRUCTIONS)
    return schema_path, instructions_path, write_tool_free_catalog(config.model, home)


def build_command(config: Config) -> list[str]:
    """Builds the command; writes the schema, instructions and catalog files as a side effect."""
    schema_path, instructions_path, catalog_path = _write_support_files(config)
    # A JSON string literal is also a valid TOML string, so json.dumps quotes paths safely.
    overrides = [*CONFIG_OVERRIDES, f"model_instructions_file={json.dumps(str(instructions_path))}"]
    # Without the catalog (model not in codex's cache) the tutor still works, with extra tools.
    if catalog_path is not None:
        overrides.append(f"model_catalog_json={json.dumps(str(catalog_path))}")
    # --ignore-user-config skips ~/.codex/config.toml (MCP servers, notify, profiles).
    # A read-only sandbox keeps any remaining tool call harmless.
    return [
        config.codex_bin,
        "exec",
        "--ignore-user-config",
        *[arg for feature in DISABLED_FEATURES for arg in ("--disable", feature)],
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--cd", str(config.home),
        "--model", config.model,
        *[arg for override in overrides for arg in ("--config", override)],
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
