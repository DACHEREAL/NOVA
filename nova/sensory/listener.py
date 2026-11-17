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
        self.dictation_mode = False

    def _get_whisper(self):
        if self._whisper_model is None:
            try:
                import os
                import warnings
                warnings.filterwarnings("ignore", category=UserWarning)
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
                from faster_whisper import WhisperModel
                # Runs locally on Apple Silicon CPU / Metal in int8 quantization (<150MB)
                self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            except Exception:
                self._whisper_model = False
        return self._whisper_model

    def _get_active_input_device(self, sd) -> tuple:
        """Dynamically detects and selects the active microphone.

        Prioritizes connected earphones/headphones/AirPods over built-in mic,
        and excludes virtual loopback devices (BlackHole, Teams, Zoom).
        """
        try:
            devices = sd.query_devices()
            default_in, _ = sd.default.device

            wearable_keywords = [
                "airpod", "headphone", "headset", "earphone", "buds",
                "bluetooth", "wireless", "usb", "external"
            ]
            virtual_keywords = ["blackhole", "teams", "zoom", "aggregate"]

            # 1. First priority: Check if any earphone / headset / AirPods is connected
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if any(v in name for v in virtual_keywords):
                        continue
                    if any(w in name for w in wearable_keywords):
                        return idx, dev.get("name", "Connected Earphones")

            # 2. Second priority: macOS system default input device
            if default_in is not None and 0 <= default_in < len(devices):
                dev = devices[default_in]
                name = dev.get("name", "").lower()
                if dev.get("max_input_channels", 0) > 0 and not any(v in name for v in virtual_keywords):
                    return default_in, dev.get("name", "System Default")

            # 3. Third priority: Built-in MacBook microphone
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if not any(v in name for v in virtual_keywords):
                        return idx, dev.get("name", "Microphone")
        except Exception:
            pass

        return None, "System Default Microphone"

    def start_listening(self):
        import sounddevice as sd
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        self.running = True

        console.print(Panel(
            f"[bold cyan]✦ N.O.V.A. Continuous Voice Daemon Active[/bold cyan]\n"
            f"[dim]Auto-detects earphones/AirPods & dynamically falls back on disconnect.[/dim]\n"
            f"[dim]Speak: 'Nova, open Safari' or 'Nova, close WhatsApp' (Ctrl+C to stop).[/dim]",
            border_style="cyan"
        ))

        # Resilient hardware auto-reconnect loop
        while self.running:
            try:
                device_id, device_name = self._get_active_input_device(sd)
                console.print(f"\n[green]🎙️  Active Input: [bold white]{device_name}[/bold white][/green]")
                print(f"🎙️  Ready and listening through '{device_name}'...")

                with sd.InputStream(
                    device=device_id,
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=audio_callback,
                    blocksize=int(self.sample_rate * 0.2),  # 200ms blocks
                ) as stream:
                    speech_buffer = []
                    is_speaking = False
                    silence_chunks = 0
                    device_check_tick = 0

                    while self.running:
                        # Detect hardware teardown or stream stoppage (e.g. closing earbuds)
                        if not stream.active or stream.stopped:
                            raise RuntimeError(f"Audio stream on '{device_name}' became inactive")

                        try:
                            chunk = AUDIO_QUEUE.get(timeout=0.25)
                        except queue.Empty:
                            if not stream.active or stream.stopped:
                                raise RuntimeError(f"Audio stream on '{device_name}' stopped")
                            device_check_tick += 1
                            # Periodically check if new audio device (e.g. earbuds plugged in) appeared
                            if device_check_tick % 12 == 0:
                                new_id, new_name = self._get_active_input_device(sd)
                                if new_id != device_id:
                                    console.print(f"\n[cyan]🎧 Audio device change detected: {new_name}. Switching...[/cyan]")
                                    break
                            continue

                        # Compute RMS audio volume
                        rms = np.sqrt(np.mean(np.square(chunk)))

                        # Voice activity threshold (~0.025 for normal voice near laptop)
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
            except Exception as stream_err:
                if not self.running:
                    break
                console.print(f"\n[bold yellow]⚠️  Audio hardware changed or disconnected: {stream_err}[/bold yellow]")
                console.print("[cyan]🔄 Seamlessly switching to system microphone in 1s...[/cyan]")
                # Drain audio queue to prevent stale buffer playback
                while not AUDIO_QUEUE.empty():
                    try:
                        AUDIO_QUEUE.get_nowait()
                    except Exception:
                        break
                # Invalidate CoreAudio / PortAudio device cache
                try:
                    sd._terminate()
                    sd._initialize()
                except Exception:
                    pass
                time.sleep(1.0)

    def _process_utterance(self, speech_chunks, console):
        if not speech_chunks:
            return

        # Attempt to use installed speech recognition backend
        transcript = self._transcribe(speech_chunks, console)
        if not transcript:
            console.print("  [dim]Could not resolve speech into words. Still listening...[/dim]\n")
            return

        console.print(f"  [yellow]Heard:[/yellow] [italic]\"{transcript}\"[/italic]")

        # Strip wake-word variations (Nova, No a, No, Hey Nova)
        clean_intent = re.sub(r"^(hey\s+)?(nova|no\s*a|no\s*v|no)[,;\s]+", "", transcript, flags=re.IGNORECASE).strip()
        if not clean_intent:
            clean_intent = transcript.strip()

        # Handle Dictation Mode Toggle
        lowered = clean_intent.lower().strip().strip(".?!,'\"")
        if lowered in ["start dictation", "dictation mode", "start typing", "enable dictation"]:
            self.dictation_mode = True
            console.print("  [bold green]📝 Dictation Mode Active! Everything you speak will be typed into your cursor.[/bold green]")
            console.print("  [dim]Say 'stop dictation' to return to normal voice commands.[/dim]\n")
            return
        elif lowered in ["stop dictation", "exit dictation", "stop typing", "end dictation", "disable dictation"]:
            self.dictation_mode = False
            console.print("  [bold yellow]🛑 Dictation Mode Deactivated. Returned to voice command mode.[/bold yellow]\n")
            return

        # If in Dictation Mode, directly type the spoken text into active cursor
        if self.dictation_mode:
            from nova.core.skills import DesktopSkills
            DesktopSkills.type_text(clean_intent + " ", use_clipboard=True)
            console.print(f"  [dim cyan]📝 Typed:[/dim cyan] [white]{clean_intent}[/white]\n")
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
                # Provide initial_prompt to bias Whisper towards assistant vocabulary
                segments, info = whisper.transcribe(
                    audio_data,
                    beam_size=1,
                    language="en",
                    initial_prompt="Nova, open Safari, close WhatsApp, Notes, Finder, arrange windows.",
                )
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
                    return r.recognize_google(audio)
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
