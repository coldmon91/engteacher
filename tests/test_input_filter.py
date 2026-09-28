import unittest

from teacherlang.input_filter import TutorInput, detect_language, select_tutor_input, strip_non_prose


class SelectTutorInputTest(unittest.TestCase):
    def test_english_prose_is_selected(self):
        result = select_tutor_input("I has went to school yesterday.", 2000)
        self.assertEqual(result.language, "en")

    def test_korean_prose_is_selected(self):
        result = select_tutor_input("이 함수에 테스트 코드를 추가해줘", 2000)
        self.assertEqual(result.language, "ko")

    def test_korean_with_english_terms_is_korean(self):
        result = select_tutor_input("hook 설정 파일을 수정해줘", 2000)
        self.assertEqual(result.language, "ko")

    def test_commands_are_skipped(self):
        self.assertIsNone(select_tutor_input("/compact please keep the summary", 2000))
        self.assertIsNone(select_tutor_input("!ls -la some dir", 2000))

    def test_short_replies_are_skipped(self):
        for prompt in ("yes", "ok go", "ㅇㅇ", "1", "네"):
            self.assertIsNone(select_tutor_input(prompt, 2000), prompt)

    def test_long_input_is_skipped(self):
        self.assertIsNone(select_tutor_input("word " * 1000, 2000))

    def test_backtick_wrapped_sentence_is_selected(self):
        result = select_tutor_input("`I has went to school yesterday.`", 2000)
        self.assertEqual(result, TutorInput(text="I has went to school yesterday.", language="en"))

    def test_code_only_prompt_is_skipped(self):
        self.assertIsNone(select_tutor_input("```\nprint('hello world here')\n```", 2000))


class StripNonProseTest(unittest.TestCase):
    def test_code_urls_paths_and_tags_are_removed(self):
        prompt = (
            "Please check `foo()` in @src/main.py and https://example.com/x\n"
            "```py\nx = 1\n```\n"
            "<pasted_content id=1>raw log</pasted_content> thanks"
        )
        self.assertEqual(strip_non_prose(prompt), "Please check {A} in and\n{B}\nthanks")

    def test_slash_inside_word_is_kept(self):
        self.assertEqual(strip_non_prose("read and/or write"), "read and/or write")

    def test_closing_tag_with_attributes_is_removed(self):
        prompt = 'hello there <pasted_content id="ab">raw log line</pasted_content id="ab"> thanks'
        self.assertEqual(strip_non_prose(prompt), "hello there thanks")

    def test_backtick_quoted_sentence_is_unwrapped(self):
        for sentence in ("I has went to school yesterday.", "Can you checks this?",
                         "이 문장을 영어로 바꿔줘"):
            self.assertEqual(strip_non_prose(f"`{sentence}`"), sentence)
        self.assertEqual(strip_non_prose("check `this sentence is fine` please"),
                         "check this sentence is fine please")

    def test_backtick_code_becomes_placeholder(self):
        for code in ("/eng", "foo()", "convertor.go", "docker images", "TKO-DECODE-RV-1",
                     "./start_service.sh --only-oauth", "10.25.17.184", "{root}/failed_record",
                     "git commit -m fix", "대안"):
            self.assertEqual(strip_non_prose(f"run `{code}` now"), "run {A} now", code)

    def test_placeholders_are_lettered_in_order_and_reused(self):
        prompt = "`[translation]` 섹션은 `원문` `개선` 과 중복이야 `[translation]` 은 제거"
        self.assertEqual(strip_non_prose(prompt), "{A} 섹션은 {B} {C} 과 중복이야 {A} 은 제거")

    def test_fenced_code_becomes_placeholder_in_order(self):
        prompt = "`foo` 대신\n```\nx = 1\n```\n이렇게 바꿔줘 ```x = 1``` 도 같아"
        self.assertEqual(strip_non_prose(prompt), "{A} 대신\n{B}\n이렇게 바꿔줘 {B} 도 같아")

    def test_unclosed_fence_runs_to_end(self):
        self.assertEqual(strip_non_prose("이 코드 봐줘\n```\nx = 1\ny = 2"), "이 코드 봐줘\n{A}")

    def test_unmatched_backticks_mid_sentence_stay_text(self):
        for prompt in ('백틱 세 개 "```" 로 묶인 경우도 치환하도록 해줘',
                       "이 코드 봐줘 ```\nx = 1\ny = 2"):
            self.assertEqual(strip_non_prose(prompt), prompt)

    def test_fence_inside_pasted_content_does_not_leak(self):
        prompt = "<pasted_content id=1>log ``` unclosed</pasted_content> 이 로그를 분석해줘"
        self.assertEqual(strip_non_prose(prompt), "이 로그를 분석해줘")

    def test_short_backtick_term_keeps_sentence(self):
        result = select_tutor_input("출력포맷 변경, `대안` 섹션은 제거", 2000)
        self.assertEqual(result, TutorInput(text="출력포맷 변경, {A} 섹션은 제거", language="ko"))

    def test_placeholders_do_not_count_as_words(self):
        self.assertIsNone(select_tutor_input("run `foo` now", 2000))
        self.assertIsNone(select_tutor_input("`./start_service.sh --only-oauth` 해줘", 2000))


class DetectLanguageTest(unittest.TestCase):
    def test_no_letters_is_none(self):
        self.assertIsNone(detect_language("123 !!!"))


if __name__ == "__main__":
    unittest.main()
