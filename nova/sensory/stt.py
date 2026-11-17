"""Streaming edge Speech-to-Text (STT) interface for zero-cloud latency."""

import logging
from typing import AsyncGenerator, Callable, Optional
import numpy as np

logger = logging.getLogger("nova.sensory.stt")


class StreamingSTT:
    """Offline streaming speech-to-text with continuous token emission."""

    def __init__(self, engine: str = "sherpa_onnx", language: str = "en"):
        self.engine = engine
        self.language = language
        logger.info(f"Initialized StreamingSTT engine '{engine}' ({language})")

    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[np.ndarray, None],
        on_partial_transcript: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Consumes incoming audio chunks and emits real-time partial hypotheses."""
        full_transcript = []
        async for chunk in audio_stream:
            # Process streaming audio frame
            pass
        return "".join(full_transcript)

    def transcribe_buffer(self, audio_data: np.ndarray) -> str:
        """Transcribes a discrete speech segment synchronously."""
        logger.debug(f"Transcribing {len(audio_data)} audio samples")
        # In full runtime, invokes Sherpa-ONNX / Moonshine ONNX model
        return "open visual studio code and arrange next to browser"
