import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engteacher.config import RECURSION_GUARD_ENV, load_config
from engteacher.input_filter import TutorInput
from engteacher.transcript import Turn
from engteacher.tutor import TutorError, build_command, parse_lesson, request_lesson

LESSON = {"mode": "correction", "needs_fix": True, "improved": "I went to school."}


def _completed(stdout, returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class RequestLessonTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        # Pinned so a provider saved from the GUI cannot change what these tests exercise.
        self.config = replace(load_config(), home=Path(self._dir.name), provider="claude",
                              model="haiku")
        self.tutor_input = TutorInput("I has went to school.", "en")

    def tearDown(self):
        self._dir.cleanup()

    def test_sends_request_on_stdin_with_guard_and_isolation(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return _completed(json.dumps({"is_error": False, "structured_output": LESSON}))

        lesson = request_lesson(self.tutor_input, [Turn("user", "hi there")], self.config, runner)

        self.assertEqual(lesson, LESSON)
        command, kwargs = calls[0]
        self.assertIn("--restricted", command)
        self.assertIn("--no-session-persistence", command)
        self.assertEqual(kwargs["env"][RECURSION_GUARD_ENV], "1")
        self.assertIn("<message>\nI has went to school.\n</message>", kwargs["input"])
        self.assertIn("[user] hi there", kwargs["input"])

    def test_nonzero_exit_raises(self):
        runner = lambda *a, **k: _completed("", returncode=1, stderr="auth failed")
        with self.assertRaisesRegex(TutorError, "auth failed"):
            request_lesson(self.tutor_input, [], self.config, runner)

    def test_timeout_raises(self):
        def runner(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

        with self.assertRaisesRegex(TutorError, "timed out"):
            request_lesson(self.tutor_input, [], self.config, runner)


class ParseLessonTest(unittest.TestCase):
    def test_rejects_invalid_outputs(self):
        for stdout in ("not json", json.dumps({"is_error": True}), json.dumps({"structured_output": {}})):
            with self.assertRaises(TutorError, msg=stdout):
                parse_lesson("claude", stdout)



class CodexBackendTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.home = Path(self._dir.name)
        self.config = replace(load_config(), home=self.home, provider="codex", model="gpt-6-luna")
        # A private CODEX_HOME holds the fake models cache the catalog is derived from.
        self.codex_home = self.home / "codex"
        self.codex_home.mkdir()
        env = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.codex_home)})
        env.start()
        self.addCleanup(env.stop)

    def _write_models_cache(self, *models):
        (self.codex_home / "models_cache.json").write_text(json.dumps({"models": list(models)}))

    def _override(self, command, key):
        values = [command[i + 1] for i, arg in enumerate(command) if arg == "--config"]
        return next((v.split("=", 1)[1] for v in values if v.startswith(f"{key}=")), None)

    def tearDown(self):
        self._dir.cleanup()

    def test_command_is_isolated_and_writes_schema(self):
        command = build_command(self.config)

        self.assertEqual(command[:2], [self.config.codex_bin, "exec"])
        for flag in ("--ignore-user-config", "--ephemeral", "--skip-git-repo-check"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-6-luna")
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        disabled = {command[i + 1] for i, arg in enumerate(command) if arg == "--disable"}
        self.assertLessEqual({"hooks", "plugins", "apps", "shell_tool", "multi_agent"}, disabled)
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        self.assertFalse(schema["additionalProperties"])

    def test_tutor_rules_replace_base_prompt_and_skills(self):
        command = build_command(self.config)

        instructions = Path(json.loads(self._override(command, "model_instructions_file")))
        self.assertIn("English writing tutor", instructions.read_text(encoding="utf-8"))
        self.assertIsNone(self._override(command, "developer_instructions"))
        self.assertEqual(self._override(command, "skills.include_instructions"), "false")
        self.assertEqual(self._override(command, "web_search"), '"disabled"')

    def test_catalog_turns_off_model_tools(self):
        self._write_models_cache(
            {"slug": "gpt-6-luna", "context_window": 272000, "tool_mode": "code_mode_only",
             "multi_agent_version": "v2", "apply_patch_tool_type": "freeform",
             "experimental_supported_tools": ["clock"]},
            {"slug": "gpt-6-sol"},
        )
        command = build_command(self.config)

        catalog = json.loads(Path(json.loads(self._override(command, "model_catalog_json"))).read_text())
        self.assertEqual(len(catalog["models"]), 1)
        entry = catalog["models"][0]
        self.assertEqual(entry["context_window"], 272000)
        self.assertEqual(entry["tool_mode"], "direct")
        self.assertEqual(entry["experimental_supported_tools"], [])
        self.assertNotIn("multi_agent_version", entry)
        self.assertNotIn("apply_patch_tool_type", entry)

    def test_uncached_model_runs_without_catalog(self):
        for cache in (None, "not json", json.dumps({"models": [{"slug": "gpt-6-sol"}]})):
            if cache is not None:
                (self.codex_home / "models_cache.json").write_text(cache)
            command = build_command(self.config)
            self.assertIsNone(self._override(command, "model_catalog_json"), msg=cache)

    def test_request_parses_final_message(self):
        runner = lambda command, **kwargs: _completed(json.dumps(LESSON))
        tutor_input = TutorInput("I has went to school.", "en")
        self.assertEqual(request_lesson(tutor_input, [], self.config, runner), LESSON)

    def test_non_json_output_raises(self):
        for stdout in ("sorry, I cannot", json.dumps({"mode": "correction"})):
            with self.assertRaises(TutorError, msg=stdout):
                parse_lesson("codex", stdout)


if __name__ == "__main__":
    unittest.main()
