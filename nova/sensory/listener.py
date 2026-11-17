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
        self._whisper_model = None

    def _get_whisper(self):
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                # Runs locally on Apple Silicon CPU / Metal in int8 quantization (<150MB)
                self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            except Exception:
                self._whisper_model = False
        return self._whisper_model

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

        # Attempt to use installed speech recognition backend
        transcript = self._transcribe(speech_chunks, console)
        if not transcript:
            console.print("  [dim]Could not resolve speech into words. Still listening...[/dim]\n")
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

    def _transcribe(self, speech_chunks, console) -> str:
        """Transcribes audio buffer using local offline Whisper first, then fallbacks."""
        audio_data = np.concatenate(speech_chunks, axis=0).flatten().astype(np.float32)

        # 1. Try Local Faster-Whisper (100% Offline & Highly Accurate)
        whisper = self._get_whisper()
        if whisper:
            try:
                segments, info = whisper.transcribe(audio_data, beam_size=1, language="en")
                text = " ".join([seg.text for seg in segments]).strip()
                if text:
                    return text
            except Exception as w_err:
                console.print(f"  [dim red]Local Whisper error: {w_err}[/dim red]")

        # 2. Try SpeechRecognition as fallback
        try:
            import speech_recognition as sr
            import io
            import wave

            pcm16 = (audio_data * 32767).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm16.tobytes())
            wav_io.seek(0)

            r = sr.Recognizer()
            r.energy_threshold = 300
            with sr.AudioFile(wav_io) as source:
                audio = r.record(source)
                try:
                    return r.recognize_google(audio, timeout=3)
                except sr.UnknownValueError:
                    console.print("  [dim yellow](Audio not recognized as speech)[/dim yellow]")
                    return ""
                except sr.RequestError as req_err:
                    console.print(f"  [red]STT Request Error (network blocked): {req_err}[/red]")
                    return ""
        except ImportError:
            console.print("  [bold red]Please run: pip install faster-whisper[/bold red]")
            return ""
        except Exception as e:
            console.print(f"  [red]Transcription error: {e}[/red]")
            return ""
