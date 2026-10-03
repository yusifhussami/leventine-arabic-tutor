"""Turn a reply into a wav the browser can play.

Gemini Flash Lite TTS returns PCM on OpenRouter. The wav wrapper is what
phones and other browsers can play. Script must match the learning language:
Arabic letters for Levantine, kana/kanji for Japanese — never bare Latin.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
import wave
from io import BytesIO

from lexicon.prefs import normalize_language

SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "google/gemini-3.8-flash-lite-tts"
VOICE = "Kore"
SAMPLE_RATE = 24000

_ARABIC = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
_ARABIC_KEEP = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\s\.\,\!\?؟،؛\-]"
)
_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_JAPANESE_KEEP = re.compile(
    r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff"
    r"\s\.\,\!\?？、。\-]"
)


def arabic_for_speech(text: str) -> str:
    """Keep only Arabic script (and light punctuation) for TTS."""
    return _script_for_speech(text, "arabic")


def text_for_speech(text: str, language: str = "arabic") -> str:
    """Keep only the learning language's script for TTS."""
    return _script_for_speech(text, language)


def _script_for_speech(text: str, language: str) -> str:
    line = " ".join((text or "").split())
    if not line:
        raise ValueError("nothing to say")
    lang = normalize_language(language)
    if lang == "japanese":
        needle, keep, label = _JAPANESE, _JAPANESE_KEEP, "Japanese"
    else:
        needle, keep, label = _ARABIC, _ARABIC_KEEP, "Arabic"
    if not needle.search(line):
        raise ValueError(f"speech needs {label} script")
    cleaned = "".join(ch if keep.match(ch) else " " for ch in line)
    cleaned = " ".join(cleaned.split())
    if not cleaned or not needle.search(cleaned):
        raise ValueError(f"speech needs {label} script")
    if len(cleaned) > 400:
        cleaned = cleaned[:400]
    return cleaned


def arabic_speech(text: str, api_key: str, opener=urllib.request.urlopen) -> bytes:
    """Return wav bytes for Arabic. Prefer speak_text for learning-language aware calls."""
    return speak_text(text, api_key, language="arabic", opener=opener)


def speech_stream_payload(
    text: str,
    api_key: str,
    language: str = "arabic",
    opener=urllib.request.urlopen,
) -> dict:
    """Second NDJSON line for /api/talk with speak=true — base64 wav or an error."""
    try:
        audio = speak_text(text, api_key, language=language, opener=opener)
    except (ValueError, RuntimeError) as exc:
        return {"audio_wav_base64": "", "error": str(exc)}
    return {"audio_wav_base64": base64.b64encode(audio).decode("ascii")}


def speak_text(
    text: str,
    api_key: str,
    language: str = "arabic",
    opener=urllib.request.urlopen,
) -> bytes:
    """Return wav bytes for the learning language. The key goes in a header."""
    line = text_for_speech(text, language)
    request = urllib.request.Request(
        SPEECH_URL,
        data=json.dumps(
            {
                "model": MODEL,
                "input": line,
                "voice": VOICE,
                "response_format": "pcm",
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=45) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"speech failed ({exc.code}): {detail}") from exc
    if not audio:
        raise RuntimeError("speech came back empty")
    if audio.startswith(b"RIFF"):
        return audio
    return _wav(audio)


def _wav(pcm: bytes) -> bytes:
    """Wrap 16-bit mono PCM so a phone browser can play it."""
    buf = BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    return buf.getvalue()
