import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engteacher.config import load_config
from engteacher.input_filter import TutorInput
from engteacher.model_settings import (
    ModelSettings,
    is_valid_model,
    load_model_settings,
    save_model_settings,
)
from engteacher.tutor import TutorError, request_lesson


class ModelSettingsStoreTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "state" / "model.json"

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_missing_file_gives_default(self):
        self.assertEqual(load_model_settings(self.path), ModelSettings("claude", "haiku"))

    def test_round_trip_keeps_other_sections(self):
        self._write({"providers": {"codex": {"model": "gpt-x", "effort": "low"}}, "note": 1})
        save_model_settings(self.path, ModelSettings("claude", "sonnet"))

        self.assertEqual(load_model_settings(self.path), ModelSettings("claude", "sonnet"))
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["providers"]["codex"], {"model": "gpt-x", "effort": "low"})
        self.assertEqual(saved["note"], 1)

    def test_unknown_provider_and_invalid_model_fall_back(self):
        self._write({"provider": "pi", "providers": {"pi": {"model": "x"}}})
        self.assertEqual(load_model_settings(self.path), ModelSettings("claude", "haiku"))
        self._write({"provider": ["claude"], "providers": {"claude": {"model": "--bad"}}})
        self.assertEqual(load_model_settings(self.path), ModelSettings("claude", "haiku"))

    def test_model_for_given_provider(self):
        self._write({"provider": "claude", "providers": {"claude": {"model": "opus"}}})
        self.assertEqual(load_model_settings(self.path, "claude").model, "opus")

    def test_save_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            save_model_settings(self.path, ModelSettings("claude", "--dangerous"))
        with self.assertRaises(ValueError):
            save_model_settings(self.path, ModelSettings("nope", "haiku"))
        self.assertFalse(self.path.exists())

    def test_model_name_rules(self):
        for name in ("haiku", "claude-sonnet-5", "claude-opus-5-5[1m]", "us.anthropic.claude:1"):
            self.assertTrue(is_valid_model(name), name)
        for name in ("", "-p", "--model", "a b", "x" * 101):
            self.assertFalse(is_valid_model(name), name)


class ConfigModelTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.home = Path(self._dir.name)
        save_model_settings(self.home / "model.json", ModelSettings("claude", "sonnet"))

    def tearDown(self):
        self._dir.cleanup()

    def test_saved_model_is_used(self):
        env = {"ENGTEACHER_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("ENGTEACHER_MODEL", None)
            config = load_config()
        self.assertEqual((config.provider, config.model), ("claude", "sonnet"))

    def test_environment_overrides_saved_model(self):
        env = {"ENGTEACHER_HOME": str(self.home), "ENGTEACHER_MODEL": "opus"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(load_config().model, "opus")


class ProviderGuardTest(unittest.TestCase):
    def test_unsupported_provider_is_reported(self):
        config = replace(load_config(), provider="pi")

        def runner(*args, **kwargs):
            raise AssertionError("no process may start for an unsupported provider")

        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(TutorError):
                request_lesson(TutorInput("I has went.", "en"), [], replace(config, home=Path(home)),
                               runner)


if __name__ == "__main__":
    unittest.main()
