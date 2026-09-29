"""Neural text-to-speech for Dadi (and the demo scammer) via Microsoft Edge's
free online voices. Audio is streamed as MP3 so playback starts before the
whole line is synthesised. The browser falls back to its built-in speech
synthesis if this fails (e.g. offline).

Voices are configurable in .env: DADI_VOICE, SCAMMER_VOICE.
Hindi: hi-IN-SwaraNeural (f), hi-IN-MadhurNeural (m).
Indian English: en-IN-NeerjaNeural (f), en-IN-PrabhatNeural (m).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import edge_tts

MAX_CHARS = 400


def voice_for(who: str) -> tuple[str, str, str]:
    """(voice, rate, pitch) for 'dadi' or 'scammer'."""
    if who == "scammer":
        return os.getenv("SCAMMER_VOICE", "hi-IN-MadhurNeural"), "+8%", "-2Hz"
    # a little slower and lower for a 78-year-old
    return os.getenv("DADI_VOICE", "hi-IN-SwaraNeural"), "-10%", "-6Hz"


async def stream(text: str, who: str = "dadi") -> AsyncIterator[bytes]:
    voice, rate, pitch = voice_for(who)
    async for chunk in edge_tts.Communicate(text[:MAX_CHARS], voice, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
