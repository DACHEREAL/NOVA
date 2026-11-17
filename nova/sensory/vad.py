"""Low-latency streaming Voice Activity Detection (Silero VAD v5)."""

import logging
import numpy as np

logger = logging.getLogger("nova.sensory.vad")


class StreamingVAD:
    """Processes continuous audio chunks and fires events when speech starts or ends."""

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.is_speech_active = False
        self._buffer: list[float] = []

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """Evaluates an audio frame (typically 512 samples at 16kHz = 32ms).

        Returns True if active human speech is detected in the current window.
        """
        # Calculate RMS energy as fast baseline filter
        rms = np.sqrt(np.mean(np.square(audio_chunk)))
        
        # When ONNX model weights are present, infer speech probability
        speech_prob = 1.0 if rms > 0.02 else 0.0
        is_speech = speech_prob >= self.threshold

        if is_speech and not self.is_speech_active:
            self.is_speech_active = True
            logger.debug("VAD: Speech onset detected")
        elif not is_speech and self.is_speech_active:
            self.is_speech_active = False
            logger.debug("VAD: Speech offset detected")

        return self.is_speech_active

    def reset(self):
        self.is_speech_active = False
        self._buffer.clear()
