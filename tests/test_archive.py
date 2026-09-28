import gzip
import json
import os
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest import mock

from engteacher.archive import list_archives, log_lock, read_archive_lines, rotate_daily
from engteacher.config import load_config
from engteacher.follow import LessonFollower
from engteacher.storage_settings import (DEFAULT_RETENTION_DAYS, StorageSettings,
                                         load_storage_settings, save_storage_settings)
from engteacher.store import append_lesson

TODAY = date.today()


def _lines(*numbers: int) -> bytes:
    return b"".join(json.dumps({"n": n}).encode() + b"\n" for n in numbers)


def _set_last_write(path: Path, day: date) -> None:
    stamp = datetime.combine(day, time(12)).timestamp()
    os.utime(path, (stamp, stamp))


class ArchiveTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.home = Path(self._dir.name)
        self.log = self.home / "lessons.jsonl"

    def tearDown(self):
        self._dir.cleanup()

    def write_log(self, data: bytes, day: date) -> None:
        self.log.write_bytes(data)
        _set_last_write(self.log, day)

    def write_archive(self, day: date, data: bytes, suffix: str = "") -> Path:
        path = self.home / f"lessons-{day.isoformat()}{suffix}.jsonl.gz"
        with gzip.open(path, "wb") as f:
            f.write(data)
        return path

    def rotate(self, retention_days: int = 0) -> None:
        with log_lock(self.log):
            rotate_daily(self.log, TODAY, retention_days)

    def archive_names(self) -> list[str]:
        return [a.path.name for a in list_archives(self.log)]


class RotateDailyTest(ArchiveTestCase):
    def test_past_day_log_is_compressed(self):
        yesterday = TODAY - timedelta(days=1)
        self.write_log(_lines(1, 2), yesterday)
        self.rotate()

        self.assertFalse(self.log.exists())
        archive = self.home / f"lessons-{yesterday.isoformat()}.jsonl.gz"
        self.assertEqual(self.archive_names(), [archive.name])
        self.assertEqual(b"".join(read_archive_lines(archive)), _lines(1, 2))
        self.assertEqual(oct(os.stat(archive).st_mode & 0o777), "0o600")

    def test_today_log_stays(self):
        self.write_log(_lines(1), TODAY)
        self.rotate()
        self.assertEqual(self.log.read_bytes(), _lines(1))
        self.assertEqual(self.archive_names(), [])

    def test_append_rotates_before_writing(self):
        yesterday = TODAY - timedelta(days=1)
        self.write_log(_lines(1), yesterday)
        append_lesson(self.log, {"n": 2}, retention_days=0)

        self.assertEqual(self.log.read_bytes(), _lines(2))
        self.assertEqual(self.archive_names(), [f"lessons-{yesterday.isoformat()}.jsonl.gz"])

    def test_same_day_gets_a_second_archive(self):
        yesterday = TODAY - timedelta(days=1)
        self.write_archive(yesterday, _lines(1))
        self.write_log(_lines(2), yesterday)
        self.rotate()

        day = yesterday.isoformat()
        self.assertEqual(self.archive_names(),
                         [f"lessons-{day}.jsonl.gz", f"lessons-{day}.2.jsonl.gz"])

    def test_retention_prunes_older_archives(self):
        for age in (15, 14, 13):
            self.write_archive(TODAY - timedelta(days=age), _lines(age))
        self.rotate(retention_days=14)
        kept = [a.day for a in list_archives(self.log)]
        self.assertEqual(kept, [TODAY - timedelta(days=14), TODAY - timedelta(days=13)])

    def test_zero_retention_keeps_everything(self):
        self.write_archive(TODAY - timedelta(days=400), _lines(1))
        self.rotate(retention_days=0)
        self.assertEqual(len(list_archives(self.log)), 1)


class CrashRecoveryTest(ArchiveTestCase):
    def test_pending_file_is_compressed(self):
        yesterday = TODAY - timedelta(days=1)
        pending = self.home / f"lessons-{yesterday.isoformat()}.jsonl"
        pending.write_bytes(_lines(1))
        self.rotate()

        self.assertFalse(pending.exists())
        self.assertEqual(self.archive_names(), [f"{pending.name}.gz"])

    def test_already_archived_pending_file_is_dropped(self):
        yesterday = TODAY - timedelta(days=1)
        self.write_archive(yesterday, _lines(1))
        pending = self.home / f"lessons-{yesterday.isoformat()}.jsonl"
        pending.write_bytes(_lines(1))
        self.rotate()

        self.assertFalse(pending.exists())
        self.assertEqual(len(list_archives(self.log)), 1)

    def test_truncated_archive_reads_what_it_can(self):
        path = self.write_archive(TODAY - timedelta(days=1), _lines(*range(2000)))
        path.write_bytes(path.read_bytes()[:-20])
        lines = read_archive_lines(path)
        self.assertGreater(len(lines), 0)
        self.assertEqual(lines[0], _lines(0))


class FollowerAcrossDaysTest(ArchiveTestCase):
    def follower(self) -> LessonFollower:
        follower = LessonFollower(self.log)
        self.addCleanup(follower.close)
        return follower

    def test_history_fills_from_archives_in_order(self):
        self.write_archive(TODAY - timedelta(days=2), _lines(1, 2))
        self.write_archive(TODAY - timedelta(days=1), _lines(3))
        self.write_log(_lines(4), TODAY)

        self.assertEqual(self.follower().history(3), [{"n": 2}, {"n": 3}, {"n": 4}])
        self.assertEqual(self.follower().history(10), [{"n": n} for n in range(1, 5)])

    def test_history_without_today_log(self):
        self.write_archive(TODAY - timedelta(days=1), _lines(1))
        self.assertEqual(self.follower().history(5), [{"n": 1}])

    def test_poll_keeps_lines_written_just_before_rotation(self):
        self.write_log(_lines(1), TODAY)
        follower = self.follower()
        follower.history(5)

        with self.log.open("ab") as f:
            f.write(_lines(2))
        _set_last_write(self.log, TODAY - timedelta(days=1))
        append_lesson(self.log, {"n": 3}, retention_days=0)

        self.assertEqual(follower.poll(), [{"n": 2}, {"n": 3}])
        self.assertEqual(follower.poll(), [])


class StorageSettingsTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.home = Path(self._dir.name)
        self.path = self.home / "storage.json"

    def tearDown(self):
        self._dir.cleanup()

    def test_missing_file_gives_default(self):
        self.assertEqual(load_storage_settings(self.path).retention_days, DEFAULT_RETENTION_DAYS)

    def test_round_trip_and_clamp(self):
        save_storage_settings(self.path, StorageSettings(retention_days=30))
        self.assertEqual(load_storage_settings(self.path).retention_days, 30)
        for saved, loaded in ((-5, 0), (9999, 365), (True, DEFAULT_RETENTION_DAYS),
                              ("7", DEFAULT_RETENTION_DAYS)):
            self.path.write_text(json.dumps({"retention_days": saved}))
            self.assertEqual(load_storage_settings(self.path).retention_days, loaded)

    def test_environment_overrides_saved_value(self):
        save_storage_settings(self.path, StorageSettings(retention_days=30))
        env = {"ENGTEACHER_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("ENGTEACHER_RETENTION_DAYS", None)
            self.assertEqual(load_config().retention_days, 30)
            os.environ["ENGTEACHER_RETENTION_DAYS"] = "0"
            self.assertEqual(load_config().retention_days, 0)
            os.environ["ENGTEACHER_RETENTION_DAYS"] = "bad"
            self.assertEqual(load_config().retention_days, 30)


if __name__ == "__main__":
    unittest.main()
