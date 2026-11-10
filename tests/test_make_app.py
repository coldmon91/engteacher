import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from teacherlang import app_bundle, make_app
from teacherlang.app_bundle import INTERPRETER_PATH, build_app


class MakeAppConfirmTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.stub = self.tmp / "stub"
        self.stub.write_bytes(b"stub-binary")
        self.app = self.tmp / "TeacherLang.app"
        for patcher in (
            mock.patch.object(app_bundle, "_sign_ad_hoc"),
            mock.patch.object(make_app, "framework_interpreter_stub", return_value=self.stub),
            mock.patch("sys.platform", "darwin"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        build_app(self.app, self.tmp, self.stub)

    def _run(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = make_app.main(["--out", str(self.app), *argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_non_interactive_stdin_fails_without_prompting(self):
        (self.app / INTERPRETER_PATH).write_bytes(b"old-binary")
        with mock.patch("sys.stdin") as stdin, mock.patch("builtins.input") as prompt:
            stdin.isatty.return_value = False
            code, _, stderr = self._run()
        self.assertEqual(code, 1)
        self.assertIn("--yes", stderr)
        prompt.assert_not_called()
        self.assertEqual((self.app / INTERPRETER_PATH).read_bytes(), b"old-binary")

    def test_yes_replaces_without_terminal(self):
        (self.app / INTERPRETER_PATH).write_bytes(b"old-binary")
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            code, _, _ = self._run("--yes")
        self.assertEqual(code, 0)
        self.assertEqual((self.app / INTERPRETER_PATH).read_bytes(), b"stub-binary")


if __name__ == "__main__":
    unittest.main()
