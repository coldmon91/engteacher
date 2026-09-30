import unittest
from datetime import datetime

from teacherlang.notes_markdown import notes_markdown

EXPORTED_AT = datetime(2026, 9, 30, 11, 40)


def _correction(time: str, original: str = "make gui simple") -> dict:
    return {
        "time": time,
        "session_id": "s1",
        "cwd": "/work/my_app",
        "language": "en",
        "original": original,
        "lesson": {
            "needs_fix": True,
            "improved": "Make the GUI simpler.",
            "issues": [{"category": "grammar", "before": "simple", "after": "simpler",
                        "explanation_ko": "비교급"}],
            "vocabulary": [{"term": "simpler", "ipa": "/ˈsɪmplər/", "note_ko": "더 단순한"}],
            "examples": ["Keep it simple."],
            "alternatives": [{"text": "Simplify the GUI.", "nuance_ko": "간결"}],
        },
    }


class NotesMarkdownTest(unittest.TestCase):
    def test_renders_every_section_of_a_card(self):
        text = notes_markdown([_correction("2026-09-28T13:55:19+09:00")], EXPORTED_AT)
        self.assertEqual(text, "\n".join([
            "# TeacherLang 노트",
            "",
            "내보낸 시각: 2026-09-30 11:40 · 노트 1개",
            "",
            "## 2026-09-28",
            "",
            "### 13:55 · my\\_app · ✎ 교정",
            "",
            "- 원문: make gui simple",
            "- 개선: **Make the GUI simpler.**",
            "",
            "#### 변경",
            "",
            "- [grammar] ~~simple~~ → **simpler**",
            "  - 비교급",
            "",
            "#### 어휘",
            "",
            "- **simpler** /ˈsɪmplər/ — 더 단순한",
            "",
            "#### 예문",
            "",
            "- Keep it simple.",
            "",
            "#### 대안",
            "",
            "- Simplify the GUI. — 간결",
        ]) + "\n")

    def test_orders_by_time_and_groups_by_day(self):
        notes = [_correction("2026-09-29T09:00:00+09:00", "b"),
                 _correction("2026-09-28T10:00:00+09:00", "a"),
                 _correction("2026-09-29T08:00:00+09:00", "c")]
        headings = [line for line in notes_markdown(notes, EXPORTED_AT).splitlines()
                    if line.startswith(("## ", "### "))]
        self.assertEqual(headings, [
            "## 2026-09-28", "### 10:00 · my\\_app · ✎ 교정",
            "## 2026-09-29", "### 08:00 · my\\_app · ✎ 교정", "### 09:00 · my\\_app · ✎ 교정",
        ])

    def test_escapes_markup_in_user_text(self):
        record = {"time": "2026-09-28T10:00:00", "original": "*a* _b_ <br> `code`\nnext",
                  "lesson": {"examples": ["# not a heading", "1. not a list", "- dash"]}}
        lines = notes_markdown([record], EXPORTED_AT).splitlines()
        self.assertIn("- 원문: \\*a\\* \\_b\\_ \\<br> `code` next", lines)
        self.assertIn("- \\# not a heading", lines)
        self.assertIn("- 1\\. not a list", lines)
        self.assertIn("- \\- dash", lines)

    def test_tolerates_missing_time_and_malformed_lesson(self):
        text = notes_markdown([{"original": "hi", "lesson": "broken"}], EXPORTED_AT)
        self.assertIn("## 날짜 없음", text)
        self.assertIn("### --:-- · - · ✓ 자연스러운 문장", text)
        self.assertIn("- 원문: hi", text)

    def test_empty_notes(self):
        self.assertEqual(notes_markdown([], EXPORTED_AT),
                         "# TeacherLang 노트\n\n내보낸 시각: 2026-09-30 11:40 · 노트 0개\n")


if __name__ == "__main__":
    unittest.main()
