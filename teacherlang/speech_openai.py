"""Turns a sentence into MP3 audio through the OpenAI speech API."""

import json
import urllib.error
import urllib.request

SPEECH_URL = "https://api.openai.com/v1/audio/speech"
MODEL = "gpt-4o-mini-tts"
INSTRUCTIONS = "Speak clearly in a natural American English accent at a moderate pace."
TIMEOUT_SEC = 20.0


class SpeechError(Exception):
    """A failure with a message safe to show: it never holds the API key or the response body."""


def synthesize(text: str, api_key: str, voice: str, timeout: float = TIMEOUT_SEC,
               urlopen=urllib.request.urlopen) -> bytes:
    if not api_key:
        raise SpeechError("설정에서 OpenAI API 키를 입력하세요.")
    body = json.dumps({
        "model": MODEL,
        "voice": voice,
        "input": text,
        "instructions": INSTRUCTIONS,
        "response_format": "mp3",
    }).encode("utf-8")
    request = urllib.request.Request(SPEECH_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        error.close()  # Releases the connection; the body is never read.
        # The error body can echo part of the key, so only the status code is kept.
        raise SpeechError(_http_error_message(error.code)) from None
    except (urllib.error.URLError, OSError) as error:  # Includes timeouts.
        raise SpeechError(f"OpenAI에 연결하지 못했습니다. ({type(error).__name__})") from None
    if not audio:
        raise SpeechError("OpenAI가 빈 음성을 보냈습니다.")
    return audio


def _http_error_message(status: int) -> str:
    if status == 401:
        return "OpenAI API 키가 올바르지 않습니다."
    if status == 429:
        return "OpenAI 사용 한도를 넘었거나 요청이 너무 많습니다."
    return f"음성을 만들지 못했습니다. (HTTP {status})"
