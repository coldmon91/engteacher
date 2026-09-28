import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from teacherlang import install
from teacherlang.settings_patch import (
    PatchResult,
    SettingsShapeError,
    apply_hook,
    build_hook_command,
    remove_hook,
)

COMMAND = "TEACHERLANG_PYTHON=/usr/bin/py /repo/bin/teacherlang-hook"
OTHER_HOOK = {"hooks": [{"type": "command", "command": "node other.js", "timeout": 5}]}


class ApplyHookTest(unittest.TestCase):
    def test_appends_after_existing_hooks(self):
        settings = {"model": "x", "hooks": {"UserPromptSubmit": [OTHER_HOOK]}}
        patched, result = apply_hook(settings, COMMAND)
        self.assertIs(result, PatchResult.ADDED)
        groups = patched["hooks"]["UserPromptSubmit"]
        self.assertEqual(groups[0], OTHER_HOOK)
        self.assertEqual(groups[1]["hooks"][0]["command"], COMMAND)
        self.assertTrue(groups[1]["hooks"][0]["async"])
        self.assertEqual(len(settings["hooks"]["UserPromptSubmit"]), 1, "input must not be mutated")

    def test_creates_missing_sections(self):
        patched, result = apply_hook({}, COMMAND)
        self.assertIs(result, PatchResult.ADDED)
        self.assertEqual(len(patched["hooks"]["UserPromptSubmit"]), 1)

    def test_same_command_is_unchanged(self):
        patched, _ = apply_hook({}, COMMAND)
        _, result = apply_hook(patched, COMMAND)
        self.assertIs(result, PatchResult.UNCHANGED)

    def test_moved_checkout_updates_instead_of_duplicating(self):
        patched, _ = apply_hook({}, COMMAND)
        moved = "TEACHERLANG_PYTHON=/usr/bin/py /new/bin/teacherlang-hook"
        updated, result = apply_hook(patched, moved)
        self.assertIs(result, PatchResult.UPDATED)
        groups = updated["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["hooks"][0]["command"], moved)

    def test_rejects_unexpected_shape(self):
        with self.assertRaises(SettingsShapeError):
            apply_hook({"hooks": []}, COMMAND)

    def test_command_quotes_paths_with_spaces(self):
        self.assertEqual(
            build_hook_command("/usr/bin/py", "/My Repo/bin/teacherlang-hook"),
            "TEACHERLANG_PYTHON=/usr/bin/py '/My Repo/bin/teacherlang-hook'",
        )


class RemoveHookTest(unittest.TestCase):
    def test_removes_only_teacherlang_group(self):
        installed, _ = apply_hook({"hooks": {"UserPromptSubmit": [OTHER_HOOK]}}, COMMAND)
        removed, result = remove_hook(installed)
        self.assertIs(result, PatchResult.REMOVED)
        self.assertEqual(removed, {"hooks": {"UserPromptSubmit": [OTHER_HOOK]}})
        self.assertEqual(len(installed["hooks"]["UserPromptSubmit"]), 2, "input must not be mutated")

    def test_keeps_other_hooks_sharing_the_group(self):
        other = OTHER_HOOK["hooks"][0]
        mine = {"type": "command", "command": COMMAND}
        settings = {"hooks": {"UserPromptSubmit": [{"hooks": [other, mine]}]}}
        removed, _ = remove_hook(settings)
        self.assertEqual(removed, {"hooks": {"UserPromptSubmit": [{"hooks": [other]}]}})

    def test_drops_containers_left_empty(self):
        installed, _ = apply_hook({"model": "x"}, COMMAND)
        removed, _ = remove_hook(installed)
        self.assertEqual(removed, {"model": "x"})

    def test_keeps_other_events(self):
        installed, _ = apply_hook({"hooks": {"Stop": [OTHER_HOOK]}}, COMMAND)
        removed, _ = remove_hook(installed)
        self.assertEqual(removed, {"hooks": {"Stop": [OTHER_HOOK]}})

    def test_not_found(self):
        for settings in ({}, {"hooks": {"UserPromptSubmit": [OTHER_HOOK]}}, {"hooks": []}):
            _, result = remove_hook(settings)
            self.assertIs(result, PatchResult.NOT_FOUND, settings)


class InstallCliTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "settings.json"
        self.original = json.dumps({"hooks": {"UserPromptSubmit": [OTHER_HOOK]}}, indent=2) + "\n"
        self.path.write_text(self.original, encoding="utf-8")
        self.path.chmod(0o644)

    def tearDown(self):
        self._dir.cleanup()

    def _run(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = install.main(["--settings", str(self.path), "--python", sys.executable, *extra])
        return code, out.getvalue(), err.getvalue()

    def _backups(self):
        return list(self.path.parent.glob("settings.json.teacherlang-backup-*"))

    def test_dry_run_does_not_write(self):
        code, out, _ = self._run("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("+", out)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self._backups(), [])

    def test_apply_writes_backup_keeps_mode_and_is_idempotent(self):
        code, _, _ = self._run("--yes")
        self.assertEqual(code, 0)
        groups = json.loads(self.path.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), self.original)

        code, out, _ = self._run("--yes")
        self.assertEqual(code, 0)
        self.assertIn("Already installed", out)
        self.assertEqual(len(self._backups()), 1)

    def test_invalid_json_is_left_untouched(self):
        self.path.write_text("{ broken", encoding="utf-8")
        code, _, err = self._run("--yes")
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ broken")

    def test_non_interactive_without_yes_aborts(self):
        original_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            code, _, err = self._run()
        finally:
            sys.stdin = original_stdin
        self.assertEqual(code, 2)
        self.assertIn("--yes", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)


    def test_uninstall_restores_original_content(self):
        self._run("--yes")
        code, out, _ = self._run("--uninstall", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("Hook removed", out)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), json.loads(self.original))
        self.assertEqual(len(self._backups()), 2)

    def test_uninstall_dry_run_and_not_found(self):
        self._run("--yes")
        installed = self.path.read_text(encoding="utf-8")
        code, _, _ = self._run("--uninstall", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), installed)

        self._run("--uninstall", "--yes")
        code, out, _ = self._run("--uninstall", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("nothing to change", out)


if __name__ == "__main__":
    unittest.main()
