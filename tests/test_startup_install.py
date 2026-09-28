import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from teacherlang import startup_install
from teacherlang.install import InstallError
from teacherlang.settings_patch import is_hook_registered

OTHER_HOOK = {"hooks": [{"type": "command", "command": "node other.js", "timeout": 5}]}
REGISTERED = {"hooks": {"UserPromptSubmit": [
    {"hooks": [{"type": "command", "command": "TEACHERLANG_PYTHON=py /old/bin/teacherlang-hook"}]}
]}}


class StartupInstallTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "settings.json"
        env = mock.patch.dict(os.environ, {"TEACHERLANG_PYTHON": sys.executable})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, settings: dict) -> str:
        text = json.dumps(settings, indent=2) + "\n"
        self.path.write_text(text, encoding="utf-8")
        return text

    def _backups(self):
        return list(self.path.parent.glob("settings.json.teacherlang-backup-*"))

    def _offer(self, *, can_prompt: bool, answer: str = "y"):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(startup_install, "_can_prompt_on_terminal", return_value=can_prompt), \
                mock.patch("builtins.input", return_value=answer), \
                redirect_stdout(out), redirect_stderr(err):
            startup_install.offer_install_in_terminal(self.path)
        return out.getvalue(), err.getvalue()

    def test_registered_hook_needs_nothing_even_with_other_command(self):
        self._write(REGISTERED)
        self.assertIsNone(startup_install.find_pending_install(self.path))

    def test_missing_hook_is_added_after_other_hooks(self):
        original = self._write({"hooks": {"UserPromptSubmit": [OTHER_HOOK]}})
        pending = startup_install.find_pending_install(self.path)
        self.assertIn("+            \"async\": true", pending.diff)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original, "finding must not write")

        backup = startup_install.apply_pending_install(pending)
        settings = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(is_hook_registered(settings))
        self.assertEqual(settings["hooks"]["UserPromptSubmit"][0], OTHER_HOOK)
        self.assertEqual(backup.read_text(encoding="utf-8"), original)

    def test_missing_settings_file_is_created_without_backup(self):
        pending = startup_install.find_pending_install(self.path)
        self.assertIsNone(startup_install.apply_pending_install(pending))
        self.assertTrue(is_hook_registered(json.loads(self.path.read_text(encoding="utf-8"))))

    def test_unexpected_shape_raises_install_error(self):
        self._write({"hooks": []})
        with self.assertRaises(InstallError):
            startup_install.find_pending_install(self.path)

    def test_change_made_meanwhile_is_not_overwritten(self):
        self._write({})
        pending = startup_install.find_pending_install(self.path)
        changed = self._write({"model": "x"})
        with self.assertRaises(InstallError):
            startup_install.apply_pending_install(pending)
        self.assertEqual(self.path.read_text(encoding="utf-8"), changed)

    def test_terminal_yes_installs(self):
        self._write({})
        out, _ = self._offer(can_prompt=True, answer="y")
        self.assertIn("Hook added", out)
        self.assertTrue(is_hook_registered(json.loads(self.path.read_text(encoding="utf-8"))))
        self.assertEqual(len(self._backups()), 1)

    def test_terminal_no_leaves_file_untouched(self):
        original = self._write({})
        out, _ = self._offer(can_prompt=True, answer="n")
        self.assertIn("Skipped", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)
        self.assertEqual(self._backups(), [])

    def test_no_terminal_only_prints_notice(self):
        original = self._write({})
        out, err = self._offer(can_prompt=False)
        self.assertEqual(out, "")
        self.assertIn("teacherlang-install", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_invalid_json_prints_notice_and_keeps_file(self):
        self.path.write_text("{ broken", encoding="utf-8")
        _, err = self._offer(can_prompt=True)
        self.assertIn("hook install skipped", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ broken")


if __name__ == "__main__":
    unittest.main()
