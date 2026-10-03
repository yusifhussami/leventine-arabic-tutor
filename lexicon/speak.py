"""Turn an Arabic reply into a wav the browser can play.

Gemini Flash Lite TTS returns PCM on OpenRouter. The wav wrapper is what
phones and other browsers can play from the response.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import wave
from io import BytesIO

SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "google/gemini-3.8-flash-lite-tts"
VOICE = "Kore"
SAMPLE_RATE = 24000


def arabic_speech(text: str, api_key: str, opener=urllib.request.urlopen) -> bytes:
    """Return wav bytes. The key goes in a header, not the URL."""
    line = " ".join(text.split())
    if not line:
        raise ValueError("nothing to say")
    if len(line) > 400:
        line = line[:400]
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
