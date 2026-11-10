import io
import json
import unittest
import urllib.error

from teacherlang.speech_openai import (
    INSTRUCTIONS,
    MODEL,
    SPEECH_URL,
    SpeechError,
    synthesize,
)

API_KEY = "sk-secret-key"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def raising(error):
    def urlopen(_request, timeout):
        raise error
    return urlopen


class SynthesizeTest(unittest.TestCase):
    def test_request_shape(self):
        captured = {}

        def urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(b"mp3-bytes")

        audio = synthesize("Hello there.", API_KEY, "marin", timeout=5, urlopen=urlopen)
        self.assertEqual(audio, b"mp3-bytes")
        request = captured["request"]
        self.assertEqual(request.full_url, SPEECH_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {API_KEY}")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {
            "model": MODEL, "voice": "marin", "input": "Hello there.",
            "instructions": INSTRUCTIONS, "response_format": "mp3",
        })
        self.assertEqual(captured["timeout"], 5)

    def test_missing_key_fails_without_request(self):
        with self.assertRaises(SpeechError) as caught:
            synthesize("Hi.", "", "marin", urlopen=raising(AssertionError("no request")))
        self.assertIn("API 키", str(caught.exception))

    def test_errors_never_leak_the_key_or_body(self):
        body = io.BytesIO(f"Incorrect API key provided: {API_KEY}".encode())
        cases = {
            401: "올바르지 않습니다",
            429: "한도",
            500: "HTTP 500",
        }
        for status, expected in cases.items():
            error = urllib.error.HTTPError(SPEECH_URL, status, "error", {}, body)
            with self.subTest(status=status), self.assertRaises(SpeechError) as caught:
                synthesize("Hi.", API_KEY, "marin", urlopen=raising(error))
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn(API_KEY, str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

    def test_network_failures(self):
        for error in (urllib.error.URLError("down"), TimeoutError("timed out")):
            with self.subTest(error=error), self.assertRaises(SpeechError) as caught:
                synthesize("Hi.", API_KEY, "marin", urlopen=raising(error))
            self.assertIn("연결하지 못했습니다", str(caught.exception))

    def test_empty_audio_is_an_error(self):
        with self.assertRaises(SpeechError):
            synthesize("Hi.", API_KEY, "marin", urlopen=lambda _r, timeout: FakeResponse(b""))


if __name__ == "__main__":
    unittest.main()
