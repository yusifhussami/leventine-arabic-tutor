import json
import unittest

from lexicon.speak import MODEL, VOICE, arabic_for_speech, arabic_speech


class _Audio:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Audio":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class SpeakTests(unittest.TestCase):
    def test_speech_asks_for_playable_arabic_audio(self) -> None:
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["auth"] = request.get_header("Authorization")
            seen["body"] = json.loads(request.data.decode())
            seen["timeout"] = timeout
            return _Audio(b"\x00\x00" * 8)

        audio = arabic_speech("  كيفك  ", "test-key", opener)
        self.assertEqual(audio[:4], b"RIFF")
        self.assertEqual(seen["url"], "https://openrouter.ai/api/v1/audio/speech")
        self.assertEqual(seen["auth"], "Bearer test-key")
        self.assertNotIn("key=", seen["url"])
        self.assertEqual(seen["body"]["model"], MODEL)
        self.assertEqual(seen["body"]["voice"], VOICE)
        self.assertEqual(seen["body"]["input"], "كيفك")
        self.assertEqual(seen["body"]["response_format"], "pcm")

    def test_blank_speech_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            arabic_speech("   ", "test-key", lambda *args: None)

    def test_romaji_and_japanese_never_reach_tts(self) -> None:
        with self.assertRaises(ValueError):
            arabic_for_speech("marhaba")
        with self.assertRaises(ValueError):
            arabic_for_speech("こんにちは")
        self.assertEqual(arabic_for_speech("  مرحبا keefak  "), "مرحبا")
