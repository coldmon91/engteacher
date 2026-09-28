"""Requests a lesson from an isolated headless tutor process (claude or codex)."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from . import tutor_claude, tutor_codex
from .config import RECURSION_GUARD_ENV, Config
from .input_filter import TutorInput
from .prompts import build_request
from .transcript import Turn
from .tutor_error import TutorError

__all__ = ["TutorError", "build_command", "parse_lesson", "request_lesson"]

Runner = Callable[..., subprocess.CompletedProcess]

# Each backend provides build_command(config) and extract_lesson(stdout).
_BACKENDS: dict[str, ModuleType] = {"claude": tutor_claude, "codex": tutor_codex}


def _backend(provider: str) -> ModuleType:
    try:
        return _BACKENDS[provider]
    except KeyError:
        raise TutorError(f"no tutor backend for provider {provider!r}") from None


def build_command(config: Config) -> list[str]:
    return _backend(config.provider).build_command(config)


def parse_lesson(provider: str, stdout: str) -> dict:
    lesson = _backend(provider).extract_lesson(stdout)
    if not isinstance(lesson, dict) or not isinstance(lesson.get("improved"), str):
        raise TutorError(f"{provider} output has no structured lesson")
    return lesson


def request_lesson(
    tutor_input: TutorInput,
    context: list[Turn],
    config: Config,
    runner: Runner = subprocess.run,
) -> dict:
    env = {**os.environ, RECURSION_GUARD_ENV: "1"}
    # A neutral working directory keeps project instruction files out of the tutor's context.
    workdir = Path(config.home)
    workdir.mkdir(parents=True, exist_ok=True)
    command = build_command(config)
    try:
        completed = runner(
            command,
            input=build_request(tutor_input, context),
            capture_output=True,
            text=True,
            timeout=config.tutor_timeout_sec,
            env=env,
            cwd=workdir,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TutorError(f"{config.provider} timed out after {config.tutor_timeout_sec}s") from exc
    except OSError as exc:
        raise TutorError(f"cannot run {command[0]}: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:300]
        raise TutorError(f"{config.provider} exited with {completed.returncode}: {detail}")
    return parse_lesson(config.provider, completed.stdout)
