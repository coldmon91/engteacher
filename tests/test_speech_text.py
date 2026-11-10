import unittest

from teacherlang.speech_text import spoken_text


def record(improved):
    return {"lesson": {"improved": improved}}


class SpokenTextTest(unittest.TestCase):
    def test_plain_sentence_is_kept(self):
        self.assertEqual(spoken_text(record("I have an apple.")), "I have an apple.")

    def test_placeholders_are_dropped_with_their_spacing(self):
        self.assertEqual(spoken_text(record("remove the {A} section")), "remove the section")
        self.assertEqual(spoken_text(record("I fixed {A}, then {AB}.")), "I fixed, then.")
        self.assertEqual(spoken_text(record("  Run\n{B}  now ")), "Run now")

    def test_nothing_to_read(self):
        self.assertEqual(spoken_text(record("{A}.")), "")
        self.assertEqual(spoken_text(record("")), "")
        self.assertEqual(spoken_text(record(None)), "")
        self.assertEqual(spoken_text({"lesson": "broken"}), "")
        self.assertEqual(spoken_text({}), "")


if __name__ == "__main__":
    unittest.main()
