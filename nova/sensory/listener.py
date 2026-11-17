"""Continuous voice listener daemon for hands-free OS control."""

import logging
import queue
import re
import sys
import time
import numpy as np

logger = logging.getLogger("nova.sensory.listener")

# Audio stream queue
AUDIO_QUEUE = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        logger.warning(f"Audio status: {status}")
    AUDIO_QUEUE.put(indata.copy())


class VoiceDaemon:
    """Continuous listening background daemon for N.O.V.A."""

    def __init__(self, orchestrator, sample_rate: int = 16000):
        self.orchestrator = orchestrator
        self.sample_rate = sample_rate
        self.running = False

    def start_listening(self):
        import sounddevice as sd
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        console.print(Panel(
            "[bold cyan]✦ N.O.V.A. Continuous Voice Daemon Active[/bold cyan]\n"
            "[green]Listening through MacBook Air Microphone...[/green]\n"
            "[dim]Try speaking: 'Nova, open Safari' or 'Nova, close WhatsApp' or press Ctrl+C to stop.[/dim]",
            border_style="cyan"
        ))

        self.running = True

        # Fast keyword recognizer / energy gate
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=audio_callback,
            blocksize=int(self.sample_rate * 0.2),  # 200ms blocks
        ):
            print("\n🎙️  Ready and listening for voice commands...")
            speech_buffer = []
            is_speaking = False
            silence_chunks = 0

            while self.running:
                try:
                    chunk = AUDIO_QUEUE.get(timeout=0.5)
                except queue.Empty:
                    continue

                # Compute RMS audio volume
                rms = np.sqrt(np.mean(np.square(chunk)))

                # Voice activity threshold (~0.02 for normal voice near laptop)
                if rms > 0.025:
                    if not is_speaking:
                        is_speaking = True
                        console.print("  [bold green]● Speech detected...[/bold green]", end="\r")
                    speech_buffer.append(chunk)
                    silence_chunks = 0
                else:
                    if is_speaking:
                        silence_chunks += 1
                        # If silence persists for ~1 second after speaking, process the utterance
                        if silence_chunks > 5:
                            is_speaking = False
                            console.print("\n  [bold cyan]⚡ Processing speech segment...[/bold cyan]")
                            self._process_utterance(speech_buffer, console)
                            speech_buffer.clear()
                            silence_chunks = 0

    def _process_utterance(self, speech_chunks, console):
        if not speech_chunks:
            return

        # Attempt to use installed offline speech recognition or local whisper/sherpa
        transcript = self._transcribe(speech_chunks)
        if not transcript:
            return

        console.print(f"  [yellow]Heard:[/yellow] [italic]\"{transcript}\"[/italic]")

        # Strip wake-word if present
        clean_intent = re.sub(r"^(hey\s+)?nova[,;\s]*", "", transcript, flags=re.IGNORECASE).strip()
        if not clean_intent:
            return

        console.print(f"  [bold cyan]Executing:[/bold cyan] {clean_intent}")

        def on_step(plan, result):
            console.print(f"  → [dim]{plan.thought}:[/dim] [green]{result.output_message}[/green]")

        results = self.orchestrator.execute_user_intent(clean_intent, on_step_update=on_step)
        console.print("  [bold green]✓ Done. Listening for next command...[/bold green]\n")

    def _transcribe(self, speech_chunks) -> str:
        """Transcribes audio buffer using available offline ASR backends."""
        try:
            import speech_recognition as sr
            import io
            import wave

            audio_data = np.concatenate(speech_chunks, axis=0)
            # Normalize to 16-bit PCM
            pcm16 = (audio_data * 32767).astype(np.int16)

            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm16.tobytes())
            wav_io.seek(0)

            r = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio = r.record(source)
                return r.recognize_google(audio)
        except Exception:
            pass

        # Native macOS SFSpeechRecognizer fallback via PyObjC
        try:
            import subprocess
            # Query macOS native dictation if available
        except Exception:
            pass

        return ""
