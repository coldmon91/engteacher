import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from teacherlang import app_bundle
from teacherlang.app_bundle import (
    BUNDLE_ID,
    INFO_PLIST_PATH,
    INTERPRETER_PATH,
    LAUNCHER_PATH,
    AppBundleError,
    build_app,
    is_teacherlang_bundle,
    render_info_plist,
    render_launcher,
)


class AppBundleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.stub = self.tmp / "stub"
        self.stub.write_bytes(b"stub-binary")
        sign = mock.patch.object(app_bundle, "_sign_ad_hoc")
        self.sign = sign.start()
        self.addCleanup(sign.stop)

    def test_info_plist_names_the_app_and_launcher(self):
        info = plistlib.loads(render_info_plist())
        self.assertEqual(info["CFBundleName"], "TeacherLang")
        self.assertEqual(info["CFBundleIdentifier"], BUNDLE_ID)
        self.assertEqual(info["CFBundleExecutable"], LAUNCHER_PATH.name)

    def test_launcher_quotes_source_root_with_apostrophe(self):
        script = render_launcher(Path("/tmp/it's here"))
        self.assertIn("PYTHONPATH='/tmp/it'\\''s here'", script)
        self.assertIn(f'exec "$DIR/{INTERPRETER_PATH.name}" -m teacherlang.gui', script)

    def test_build_creates_bundle_and_signs_interpreter(self):
        app = self.tmp / "out" / "TeacherLang.app"
        build_app(app, Path("/src"), self.stub)
        self.assertTrue(is_teacherlang_bundle(app))
        self.assertEqual((app / INTERPRETER_PATH).read_bytes(), b"stub-binary")
        self.assertTrue((app / LAUNCHER_PATH).stat().st_mode & 0o100)
        self.sign.assert_called_once()
        self.assertEqual([p.name for p in app.parent.iterdir()], ["TeacherLang.app"])

    def test_build_replaces_existing_bundle(self):
        app = self.tmp / "TeacherLang.app"
        build_app(app, Path("/old"), self.stub)
        build_app(app, Path("/new"), self.stub)
        self.assertIn("/new", (app / LAUNCHER_PATH).read_text())

    def test_build_refuses_to_replace_foreign_directory(self):
        foreign = self.tmp / "TeacherLang.app"
        (foreign / "Contents").mkdir(parents=True)
        (foreign / "keep.txt").write_text("mine")
        with self.assertRaises(AppBundleError):
            build_app(foreign, Path("/src"), self.stub)
        self.assertTrue((foreign / "keep.txt").exists())
        self.assertFalse((foreign / INFO_PLIST_PATH).exists())


if __name__ == "__main__":
    unittest.main()
