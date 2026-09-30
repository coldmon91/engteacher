import json
import tempfile
import unittest
from pathlib import Path

from teacherlang import transcript
from teacherlang.transcript import Turn, recent_turns


def _user(content, **extra):
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def _assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


class RecentTurnsTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "session.jsonl"

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, records, trailing=""):
        lines = [json.dumps(r) for r in records]
        self.path.write_text("\n".join(lines) + "\n" + trailing, encoding="utf-8")

    def test_keeps_typed_text_and_assistant_text_only(self):
        self._write([
            _user("first question"),
            _assistant({"type": "thinking", "thinking": "hidden"}, {"type": "tool_use", "name": "Bash"}),
            _user([{"type": "tool_result", "content": "output"}]),
            _assistant({"type": "text", "text": "an answer"}),
            _user("<command-name>/clear</command-name>"),
            _user("meta text", isMeta=True),
            _user("side question", isSidechain=True),
            {"type": "attachment"},
        ], trailing="{broken json")
        turns = recent_turns(str(self.path), max_turns=10, max_chars_per_turn=100)
        self.assertEqual(turns, [Turn("user", "first question"), Turn("assistant", "an answer")])

    def test_limits_turns_and_length(self):
        self._write([_user(f"message number {i}") for i in range(5)])
        turns = recent_turns(str(self.path), max_turns=2, max_chars_per_turn=10)
        self.assertEqual([t.text for t in turns], ["message n…", "message n…"])

    def test_excludes_current_prompt(self):
        self._write([_user("earlier"), _user("current prompt")])
        turns = recent_turns(str(self.path), 5, 100, exclude_text="current prompt")
        self.assertEqual(turns, [Turn("user", "earlier")])

    def test_clean_text_runs_before_truncation_and_drops_empty_turns(self):
        self._write([_user("older one"), _user("CODE CODE keep this"), _user("CODE")])
        turns = recent_turns(str(self.path), 2, 9,
                             clean_text=lambda text: text.replace("CODE", "").strip())
        self.assertEqual(turns, [Turn("user", "older one"), Turn("user", "keep this")])

    def test_clean_text_sees_newest_turn_first(self):
        self._write([_user("old"), _user("new")])
        seen = []
        recent_turns(str(self.path), 1, 100, clean_text=lambda text: seen.append(text) or text)
        self.assertEqual(seen, ["new"])

    def test_reads_only_the_tail_of_large_files(self):
        original = transcript.TAIL_READ_BYTES
        transcript.TAIL_READ_BYTES = 200
        try:
            self._write([_user("x" * 300), _user("latest")])
            turns = recent_turns(str(self.path), 5, 1000)
        finally:
            transcript.TAIL_READ_BYTES = original
        self.assertEqual(turns, [Turn("user", "latest")])

    def test_missing_file_returns_empty(self):
        self.assertEqual(recent_turns(str(self.path), 5, 100), [])
        self.assertEqual(recent_turns(None, 5, 100), [])


if __name__ == "__main__":
    unittest.main()
