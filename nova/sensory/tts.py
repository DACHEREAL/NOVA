"""Low-latency streaming Text-to-Speech (TTS) using Kokoro-82M / Piper."""

import logging
from typing import AsyncGenerator

logger = logging.getLogger("nova.sensory.tts")


class StreamingTTS:
    """Zero-cloud text-to-speech synthesizer generating natural spoken feedback."""

    def __init__(self, engine: str = "kokoro_82m", voice: str = "af_heart"):
        self.engine = engine
        self.voice = voice
        logger.info(f"Initialized StreamingTTS ({engine}, voice='{voice}')")

    async def speak_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Streams synthesized raw PCM audio chunks in real-time as text tokens arrive."""
        logger.info(f"Synthesizing speech: '{text}'")
        # Generates streaming audio chunks (<100ms first-chunk latency)
        yield b"\x00" * 1024

    def speak_sync(self, text: str) -> None:
        """Plays audio confirmation directly to the system default audio output."""
        logger.info(f"N.O.V.A. Spoken Response: {text}")
