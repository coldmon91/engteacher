import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from teacherlang.config import load_config
from teacherlang.follow import LessonFollower
from teacherlang.hook import handle_event
from teacherlang.transcript import Turn
from teacherlang.render import (
    ANSI_CODES,
    DETAIL,
    FIELD,
    HEADER,
    HEADLINE,
    ITEM,
    SECTION,
    Span,
    Style,
    has_alternatives,
    lesson_blocks,
    lesson_lines,
    render_lesson,
)
from teacherlang.store import append_lesson

LESSON = {
    "mode": "correction",
    "needs_fix": True,
    "improved": "I went to school yesterday.",
    "alternatives": [{"text": "I was at school yesterday.", "nuance_ko": "상태 강조"}],
    "issues": [{"category": "grammar", "before": "has went", "after": "went", "explanation_ko": "과거 시제"}],
    "vocabulary": [{"term": "yesterday", "ipa": "/ˈjɛstərdeɪ/", "note_ko": "첫 음절 강세"}],
    "examples": ["I went home early yesterday."],
}


class HandleEventTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.config = replace(load_config(), home=Path(self._dir.name))

    def tearDown(self):
        self._dir.cleanup()

    def test_logs_lesson_for_prose(self):
        event = {"prompt": "I has went to school yesterday.", "session_id": "s1", "cwd": "/tmp/proj"}
        record = handle_event(event, self.config, request_lesson=lambda *a: LESSON)

        self.assertEqual(record["lesson"], LESSON)
        self.assertEqual(oct(os.stat(self.config.lessons_path).st_mode & 0o777), "0o600")
        follower = LessonFollower(self.config.lessons_path)
        self.addCleanup(follower.close)
        self.assertEqual(follower.history(5), [record])

    def test_context_shares_placeholders_with_message(self):
        transcript = Path(self._dir.name) / "session.jsonl"
        earlier = {"type": "user", "message": {"role": "user",
                   "content": "`foo()` 와 `bar()` 차이 알려줘\n<pasted_content>raw log</pasted_content>"}}
        transcript.write_text(json.dumps(earlier) + "\n", encoding="utf-8")
        event = {"prompt": "`bar()` 는 어디서 호출돼", "transcript_path": str(transcript)}
        seen = {}

        def capture(tutor_input, context, config):
            seen.update(text=tutor_input.text, context=context)
            return LESSON

        handle_event(event, self.config, request_lesson=capture)
        self.assertEqual(seen["text"], "{A} 는 어디서 호출돼")
        self.assertEqual(seen["context"], [Turn("user", "{B} 와 {A} 차이 알려줘")])

    def test_natural_english_is_not_logged(self):
        natural = {**LESSON, "needs_fix": False, "improved": "I went to school yesterday."}
        event = {"prompt": "I went to school yesterday.", "session_id": "s1", "cwd": "/tmp/proj"}

        self.assertIsNone(handle_event(event, self.config, request_lesson=lambda *a: natural))
        self.assertFalse(self.config.lessons_path.exists())

    def test_skipped_prompt_does_not_call_tutor(self):
        def fail(*args):
            raise AssertionError("tutor must not be called")

        self.assertIsNone(handle_event({"prompt": "/clear"}, self.config, request_lesson=fail))
        self.assertFalse(self.config.lessons_path.exists())


class LessonFollowerTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "lessons.jsonl"

    def tearDown(self):
        self._dir.cleanup()

    def test_history_then_new_lines(self):
        for i in range(3):
            append_lesson(self.path, {"n": i}, retention_days=0)
        follower = LessonFollower(self.path)
        self.addCleanup(follower.close)
        self.assertEqual(follower.history(2), [{"n": 1}, {"n": 2}])
        self.assertEqual(follower.poll(), [])

        with self.path.open("a", encoding="utf-8") as f:
            f.write('{"n": 3}\n{"n":')
        self.assertEqual(follower.poll(), [{"n": 3}])
        with self.path.open("a", encoding="utf-8") as f:
            f.write(" 4}\n")
        self.assertEqual(follower.poll(), [{"n": 4}])

    def test_restarts_after_rotation(self):
        append_lesson(self.path, {"n": 1}, retention_days=0)
        follower = LessonFollower(self.path)
        self.addCleanup(follower.close)
        follower.history(5)
        self.path.unlink()
        append_lesson(self.path, {"n": 2}, retention_days=0)
        self.assertEqual(follower.poll(), [{"n": 2}])

    def test_missing_file(self):
        follower = LessonFollower(self.path)
        self.addCleanup(follower.close)
        self.assertEqual(follower.history(5), [])
        self.assertEqual(follower.poll(), [])


class RenderLessonTest(unittest.TestCase):
    def test_renders_all_sections_without_color(self):
        record = {"time": "2026-09-28T10:00:00+09:00", "cwd": "/x/teacherlang", "language": "en",
                  "original": "I has went to school yesterday.", "lesson": LESSON}
        text = render_lesson(record, Style(enabled=False))
        for expected in ("10:00:00 · teacherlang", "✎ 교정", "I went to school yesterday.",
                         "has went → went", "/ˈjɛstərdeɪ/", "I went home early"):
            self.assertIn(expected, text)
        self.assertNotIn("대안", text)
        self.assertNotIn("상태 강조", text)
        self.assertNotIn("\033[", text)

    def test_tolerates_malformed_lesson(self):
        text = render_lesson({"original": "hi", "lesson": {"issues": "bad"}}, Style(enabled=False))
        self.assertIn("hi", text)

    def test_translation_issues_are_hidden(self):
        translation = {"category": "translation", "before": "보여줘", "after": "show me",
                       "explanation_ko": "명령형 번역"}
        grammar = {"category": "grammar", "before": "a diffs", "after": "a diff",
                   "explanation_ko": "단수형"}
        record = {"language": "ko", "original": "diff 보여줘",
                  "lesson": {"improved": "Show me the diff.", "issues": [translation]}}
        text = render_lesson(record, Style(enabled=False))
        self.assertNotIn("[translation]", text)
        self.assertNotIn("변경", text)

        record["lesson"]["issues"] = [translation, grammar]
        text = render_lesson(record, Style(enabled=False))
        self.assertNotIn("[translation]", text)
        self.assertIn("[grammar] a diffs → a diff", text)

    def test_color_wraps_tagged_spans_only(self):
        text = render_lesson({"original": "hi", "lesson": {"improved": "Hi!"}}, Style(enabled=True))
        self.assertIn("\033[1mHi!\033[0m", text)
        self.assertIn("\033[0mhi", text)


class LessonLinesTest(unittest.TestCase):
    def test_spans_carry_tags_for_gui(self):
        record = {"language": "en", "original": "I has went to school yesterday.", "lesson": LESSON}
        spans = [span for line in lesson_lines(record) for span in line]
        self.assertIn(Span("has went", "red"), spans)
        self.assertIn(Span("went", "green"), spans)
        self.assertIn(Span("/ˈjɛstərdeɪ/", "cyan"), spans)
        self.assertIn(Span("I went to school yesterday.", "bold"), spans)
        self.assertTrue({span.tag for span in spans} <= set(ANSI_CODES) | {None})

    def test_alternatives_are_shown_only_on_request(self):
        record = {"language": "en", "original": "I has went to school yesterday.", "lesson": LESSON}
        self.assertTrue(has_alternatives(record))
        hidden = [span.text for line in lesson_lines(record) for span in line]
        self.assertNotIn("대안", hidden)
        shown = [span.text for line in lesson_lines(record, show_alternatives=True) for span in line]
        self.assertIn("대안", shown)
        self.assertIn("    · I was at school yesterday. ", shown)
        self.assertIn("— 상태 강조", shown)

    def test_has_alternatives_tolerates_malformed_lesson(self):
        self.assertFalse(has_alternatives({"original": "hi"}))
        self.assertFalse(has_alternatives({"lesson": {"alternatives": "bad"}}))
        self.assertFalse(has_alternatives({"lesson": "bad"}))

    def test_header_rule_can_be_dropped(self):
        record = {"time": "2026-09-28T13:04:00", "cwd": "/x/teacherlang", "original": "hi"}
        self.assertIn("─", lesson_lines(record)[0][0].text)
        self.assertEqual(lesson_lines(record, header_rule=False)[0],
                         [Span("13:04:00 · teacherlang", "dim")])

    def test_gui_defines_every_tag(self):
        from teacherlang import gui

        self.assertEqual(set(gui.TAG_COLORS) | gui.FONT_TAGS, set(ANSI_CODES))


class LessonBlocksTest(unittest.TestCase):
    def test_blocks_carry_kinds_without_indentation(self):
        record = {"time": "2026-09-28T13:04:00", "cwd": "/x/teacherlang", "language": "en",
                  "original": "I has went to school yesterday.", "lesson": LESSON}
        blocks = lesson_blocks(record, show_alternatives=True)
        self.assertEqual([block.kind for block in blocks], [
            HEADER, HEADLINE, FIELD, FIELD,
            SECTION, ITEM, DETAIL,
            SECTION, ITEM,
            SECTION, ITEM,
            SECTION, ITEM,
        ])
        self.assertEqual([block.label for block in blocks if block.kind in (FIELD, SECTION)],
                         ["원문", "개선", "변경", "어휘", "예문", "대안"])
        self.assertEqual(blocks[6].spans, [Span("과거 시제")])
        self.assertEqual(blocks[10].spans, [Span("I went home early yesterday.")])
        self.assertEqual(blocks[-1].spans[0], Span("I was at school yesterday. "))
        leading = [block.spans[0].text for block in blocks if block.spans]
        self.assertFalse([text for text in leading if text.startswith(" ")])

    def test_lines_match_blocks(self):
        record = {"language": "en", "original": "I has went to school yesterday.", "lesson": LESSON}
        self.assertEqual(len(lesson_lines(record, show_alternatives=True)),
                         len(lesson_blocks(record, show_alternatives=True)))
        self.assertEqual(lesson_lines(record)[-1], [Span("    · I went home early yesterday.")])


if __name__ == "__main__":
    unittest.main()
