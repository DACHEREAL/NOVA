"""Continuous voice listener daemon for hands-free OS control.

Industrial-grade implementation with:
- Bulletproof audio device recovery (earbuds disconnect, mic changes)
- Graceful Whisper model loading with instant fallback
- Signal-safe shutdown (SIGINT sets flag instead of crashing)
- Full exception isolation: command processing NEVER kills the listener
"""

import logging
import os
import queue
import re
import signal
import sys
import time
import traceback

import numpy as np

logger = logging.getLogger("nova.sensory.listener")

# Audio stream queue
AUDIO_QUEUE: queue.Queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    """PortAudio callback — drops data silently on overflow instead of crashing."""
    try:
        if status:
            logger.debug(f"Audio status: {status}")
        AUDIO_QUEUE.put(indata.copy())
    except Exception:
        pass  # Never let callback crash — it would kill the whole stream


# Wake-word regex: "Nova", "Hey Nova", "nova,", "Nova.", case-insensitive
# Also handles Whisper artifacts like "No va", "Noava", "No a", "Noa"
WAKE_WORD_RE = re.compile(
    r"^(hey\s+)?(nova|no\s*v\s*a|no\s*a|noa|no va)[,;:\s!.\-]+",
    re.IGNORECASE,
)

# How many 200ms silence chunks before we consider speech finished (~1.4s)
SILENCE_CHUNKS_THRESHOLD = 7

# RMS threshold for voice activity detection
VAD_THRESHOLD = 0.02


class VoiceDaemon:
    """Continuous listening background daemon for N.O.V.A.

    Designed to run indefinitely without crashing, even when:
    - Bluetooth earbuds disconnect mid-sentence
    - Audio devices change (dock/undock)
    - Whisper model fails to load
    - Command processing throws errors
    """

    def __init__(self, orchestrator, sample_rate: int = 16000):
        self.orchestrator = orchestrator
        self.sample_rate = sample_rate
        self.running = False
        self._whisper_model = None
        self._whisper_attempted = False  # Only try loading once
        self.dictation_mode = False

    def _get_whisper(self):
        """Loads Whisper model ONCE. If it fails, never retries (uses fallback)."""
        if self._whisper_attempted:
            return self._whisper_model if self._whisper_model else None
        self._whisper_attempted = True

        try:
            # Suppress ALL HuggingFace warnings BEFORE importing
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            os.environ["TOKENIZERS_PARALLELISM"] = "false"

            import warnings
            warnings.filterwarnings("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", category=FutureWarning)
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            logging.getLogger("faster_whisper").setLevel(logging.ERROR)

            from faster_whisper import WhisperModel

            # Use base.en — small enough to download without auth, good enough accuracy
            self._whisper_model = WhisperModel(
                "base.en", device="cpu", compute_type="int8"
            )
            logger.info("Whisper base.en model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load Whisper model: {e}")
            self._whisper_model = None

        return self._whisper_model

    def _get_active_input_device(self, sd) -> tuple:
        """Detects active microphone. Prioritizes earphones/headsets over built-in mic."""
        try:
            devices = sd.query_devices()
            default_in = sd.default.device[0]

            wearable_keywords = [
                "airpod", "headphone", "headset", "earphone", "buds",
                "bluetooth", "wireless", "usb", "external",
            ]
            virtual_keywords = ["blackhole", "teams", "zoom", "aggregate", "soundflower"]

            # Priority 1: Connected earphone / headset / AirPods
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if any(v in name for v in virtual_keywords):
                        continue
                    if any(w in name for w in wearable_keywords):
                        return idx, dev.get("name", "Connected Earphones")

            # Priority 2: macOS system default input device
            if default_in is not None and 0 <= default_in < len(devices):
                dev = devices[default_in]
                name = dev.get("name", "").lower()
                if dev.get("max_input_channels", 0) > 0 and not any(v in name for v in virtual_keywords):
                    return default_in, dev.get("name", "System Default")

            # Priority 3: Any available input device
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if not any(v in name for v in virtual_keywords):
                        return idx, dev.get("name", "Microphone")
        except Exception as e:
            logger.debug(f"Device detection error: {e}")

        return None, "System Default Microphone"

    def _reinitialize_audio(self, sd):
        """Drain the audio queue and hard-reset the PortAudio backend."""
        # Drain stale audio buffers
        drained = 0
        while not AUDIO_QUEUE.empty():
            try:
                AUDIO_QUEUE.get_nowait()
                drained += 1
            except Exception:
                break
        if drained:
            logger.debug(f"Drained {drained} stale audio buffers")

        # Hard reset PortAudio to pick up device changes
        try:
            sd._terminate()
        except Exception:
            pass
        try:
            sd._initialize()
        except Exception:
            pass

    def start_listening(self):
        """Main entry point. NEVER crashes — survives ALL audio/processing errors."""
        try:
            import sounddevice as sd
        except ImportError as e:
            print(f"[NOVA] Cannot import sounddevice: {e}")
            print("[NOVA] Install it with: pip install sounddevice")
            return

        # Set up signal handler for graceful shutdown
        original_sigint = signal.getsignal(signal.SIGINT)

        def _signal_handler(signum, frame):
            self.running = False
            print("\n[NOVA] Shutting down gracefully...")

        signal.signal(signal.SIGINT, _signal_handler)

        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
        except ImportError:
            class _FallbackConsole:
                def print(self, *args, **kwargs):
                    # Strip rich markup for plain output
                    text = str(args[0]) if args else ""
                    text = re.sub(r"\[/?[^\]]+\]", "", text)
                    print(text, **{k: v for k, v in kwargs.items() if k == "end"})
            class Panel:
                def __init__(self, *a, **kw):
                    pass
            console = _FallbackConsole()

        self.running = True

        # Display startup banner
        try:
            ai_status = (
                f"[bold green]● Active[/bold green] ([white]{self.orchestrator.ai_engine.active_model}[/white])"
                if self.orchestrator.ai_engine.is_available
                else "[yellow]Standby / Reflex Router[/yellow] [dim](Run 'ollama run llama3.2' for full AI)[/dim]"
            )
            habits_count = len(self.orchestrator.habits.recent_interactions)

            console.print(Panel(
                f"[bold cyan]✦ N.O.V.A. Autonomous Desktop OS Agent Active[/bold cyan]\n\n"
                f"🧠 [bold]Local AI Brain (LLaMA):[/bold] {ai_status}\n"
                f"📊 [bold]Habit Learning Memory:[/bold] [green]{habits_count} interactions learned[/green]\n"
                f"🎙️ [bold]Adaptive Audio:[/bold] Dynamically switches between Earphones & Mac Mic\n\n"
                f"[dim]Speak naturally: 'open fb on chrome', 'tell frosty I'll be late on whatsapp', 'type help in dictionary'[/dim]",
                border_style="cyan",
            ))
        except Exception:
            print("✦ N.O.V.A. Active — Listening for voice commands...")

        # === MAIN RESILIENT LOOP ===
        # This outer loop NEVER exits except when self.running is set to False
        while self.running:
            try:
                self._run_audio_session(sd, console)
            except Exception as e:
                if not self.running:
                    break
                logger.error(f"Audio session crashed: {e}")
                try:
                    console.print(f"\n[bold yellow]⚠️  Audio error: {e}. Recovering...[/bold yellow]")
                except Exception:
                    print(f"\n⚠️  Audio error: {e}. Recovering...")

            if not self.running:
                break

            # Recovery: reinitialize audio and retry after a pause
            try:
                self._reinitialize_audio(sd)
            except Exception:
                pass
            time.sleep(2.0)

            # Announce new device
            try:
                _, new_name = self._get_active_input_device(sd)
                console.print(f"\n[cyan]🔄 Switching to: {new_name}[/cyan]")
            except Exception:
                pass

        # Restore original signal handler
        signal.signal(signal.SIGINT, original_sigint)
        print("Voice listener stopped.")

    def _run_audio_session(self, sd, console):
        """Runs ONE audio capture session. Raises on device failure (caller handles recovery)."""
        device_id, device_name = self._get_active_input_device(sd)
        console.print(f"\n[green]🎙️  Active Input: [bold white]{device_name}[/bold white][/green]")
        print(f"🎙️  Ready and listening through '{device_name}'...")

        # Open audio stream — may raise if device is unavailable
        stream = sd.InputStream(
            device=device_id,
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=audio_callback,
            blocksize=int(self.sample_rate * 0.2),  # 200ms blocks
        )

        with stream:
            speech_buffer = []
            is_speaking = False
            silence_chunks = 0
            device_check_counter = 0

            while self.running:
                # Check stream health
                try:
                    if not stream.active or stream.stopped:
                        raise RuntimeError(f"Audio stream on '{device_name}' became inactive")
                except Exception:
                    raise RuntimeError(f"Audio stream on '{device_name}' lost")

                # Get audio chunk
                try:
                    chunk = AUDIO_QUEUE.get(timeout=0.3)
                except queue.Empty:
                    device_check_counter += 1
                    # Every ~3 seconds, check if a new device appeared
                    if device_check_counter % 10 == 0:
                        try:
                            new_id, new_name = self._get_active_input_device(sd)
                            if new_id != device_id:
                                console.print(f"\n[cyan]🎧 New audio device detected: {new_name}. Switching...[/cyan]")
                                return  # Exit this session, outer loop will reconnect
                        except Exception:
                            pass
                    continue

                # Voice activity detection via RMS
                try:
                    rms = float(np.sqrt(np.mean(np.square(chunk))))
                except Exception:
                    continue

                if rms > VAD_THRESHOLD:
                    if not is_speaking:
                        is_speaking = True
                        try:
                            console.print("  [bold green]● Speech detected...[/bold green]")
                        except Exception:
                            pass
                    speech_buffer.append(chunk)
                    silence_chunks = 0
                else:
                    if is_speaking:
                        silence_chunks += 1
                        if silence_chunks > SILENCE_CHUNKS_THRESHOLD:
                            is_speaking = False
                            try:
                                console.print("  [bold cyan]⚡ Processing speech segment...[/bold cyan]")
                            except Exception:
                                pass
                            # Process in a fully isolated try/except
                            self._safe_process_utterance(speech_buffer, console)
                            speech_buffer.clear()
                            silence_chunks = 0

    def _safe_process_utterance(self, speech_chunks, console):
        """Wrapper that NEVER lets processing errors kill the listener."""
        try:
            self._process_utterance(speech_chunks, console)
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            try:
                console.print(f"  [red]Error processing command: {e}[/red]")
                console.print("  [bold green]✓ Done. Listening for next command...[/bold green]\n")
            except Exception:
                print(f"  Error: {e}")
                print("  Still listening...")

    def _process_utterance(self, speech_chunks, console):
        """Transcribes audio and executes the voice command."""
        if not speech_chunks:
            return

        transcript = self._transcribe(speech_chunks, console)
        if not transcript:
            console.print("  [dim]Could not resolve speech. Still listening...[/dim]\n")
            return

        console.print(f"  [yellow]Heard:[/yellow] [italic]\"{transcript}\"[/italic]")

        # Strip wake-word
        clean_intent = WAKE_WORD_RE.sub("", transcript).strip()
        if not clean_intent:
            clean_intent = transcript.strip()

        # Remove trailing punctuation artifacts from Whisper
        clean_intent = clean_intent.rstrip(".!?,;:")

        # Handle Dictation Mode Toggle
        lowered = clean_intent.lower().strip()
        if lowered in ["start dictation", "dictation mode", "start typing", "enable dictation"]:
            self.dictation_mode = True
            console.print("  [bold green]📝 Dictation Mode Active![/bold green]")
            console.print("  [dim]Say 'stop dictation' to return to voice commands.[/dim]\n")
            return
        elif lowered in ["stop dictation", "exit dictation", "stop typing", "end dictation", "disable dictation"]:
            self.dictation_mode = False
            console.print("  [bold yellow]🛑 Dictation Mode Off. Voice command mode active.[/bold yellow]\n")
            return

        # Dictation mode: type everything spoken
        if self.dictation_mode:
            from nova.core.skills import DesktopSkills
            DesktopSkills.type_text(clean_intent + " ", use_clipboard=True)
            console.print(f"  [dim cyan]📝 Typed:[/dim cyan] [white]{clean_intent}[/white]\n")
            return

        console.print(f"  [bold cyan]Executing:[/bold cyan] {clean_intent}")

        # Determine engine BEFORE execution
        uses_ai_brain = self.orchestrator.ai_engine.is_available

        def on_step(plan, result):
            try:
                console.print(f"  → [dim]{plan.thought}:[/dim] [green]{result.output_message}[/green]")
            except Exception:
                pass

        # Execute the command
        results = self.orchestrator.execute_user_intent(clean_intent, on_step_update=on_step)

        # Print which engine handled it
        if uses_ai_brain:
            print("  🧠 AI Brain")
        else:
            print("  ⚡ Reflex Router")

        console.print("  [bold green]✓ Done. Listening for next command...[/bold green]\n")

    def _transcribe(self, speech_chunks, console) -> str:
        """Transcribes audio. Uses local Whisper first, falls back to SpeechRecognition."""
        try:
            audio_data = np.concatenate(speech_chunks, axis=0).flatten().astype(np.float32)
        except Exception as e:
            logger.error(f"Audio concatenation error: {e}")
            return ""

        # 1. Try Local Faster-Whisper (offline, accurate)
        whisper = self._get_whisper()
        if whisper:
            try:
                segments, info = whisper.transcribe(
                    audio_data,
                    beam_size=1,
                    language="en",
                    vad_filter=True,
                    word_timestamps=False,
                    initial_prompt="Nova, open Safari, close WhatsApp, type help in dictionary, search on YouTube.",
                )
                text = " ".join([seg.text for seg in segments]).strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"Whisper transcription error: {e}")

        # 2. Fallback: SpeechRecognition (requires network for Google STT)
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
                    return ""
                except sr.RequestError:
                    console.print("  [dim yellow](Google STT unavailable — network blocked)[/dim yellow]")
                    return ""
        except ImportError:
            console.print("  [bold red]No speech backend available. Install faster-whisper or SpeechRecognition.[/bold red]")
            return ""
        except Exception as e:
            logger.warning(f"Fallback transcription error: {e}")
            return ""
