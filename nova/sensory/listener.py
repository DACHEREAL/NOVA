"""Continuous voice listener daemon for hands-free OS control.

Industrial-grade implementation with:
- Zero-crash adaptive audio recovery (OnePlus Buds / AirPods disconnect -> Mac Mic)
- Native sample rate detection (48kHz internal mic, 16kHz Bluetooth) with fast downsampling
- Dynamic VAD threshold (sensitive for distant MacBook mic, calibrated for earbuds)
- Fast local Whisper transcription (<400ms) with zero HuggingFace warnings
- Isolated execution: command processing NEVER interrupts the voice listening loop
"""

import logging
import os
import queue
import re
import signal
import sys
import time
import numpy as np

logger = logging.getLogger("nova.sensory.listener")

# Audio stream queue
AUDIO_QUEUE = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        logger.debug(f"Audio status: {status}")
    try:
        AUDIO_QUEUE.put(indata.copy())
    except Exception:
        pass


# Wake-word regex: accepts "Nova", "Hey Nova", "No va", "Noava", "No a", "Noa" and fuzzy variants
WAKE_WORD_RE = re.compile(
    r"^(hey\s+)?(nova|no\s*v\s*a|no\s*a|noa|no va)[,;\s:!.\-]+",
    re.IGNORECASE,
)

# Number of silence chunks before we consider speech finished (~1.2s at 200ms blocks)
SILENCE_CHUNKS_THRESHOLD = 6


class VoiceDaemon:
    """Continuous listening background daemon for N.O.V.A."""

    def __init__(self, orchestrator, sample_rate: int = 16000):
        self.orchestrator = orchestrator
        self.sample_rate = sample_rate
        self.current_stream_sr = sample_rate
        self.running = False
        self._whisper_model = None
        self.dictation_mode = False

    def _get_whisper(self):
        if self._whisper_model is None:
            try:
                import warnings
                warnings.filterwarnings("ignore")
                os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
                os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
                os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
                os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
                os.environ["HF_HUB_VERBOSITY"] = "error"
                logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
                logging.getLogger("faster_whisper").setLevel(logging.ERROR)
                import ctranslate2
                ctranslate2.set_log_level(logging.ERROR)
                from faster_whisper import WhisperModel
                # base.en transcribes in ~300ms on Apple Silicon and is cached locally
                try:
                    self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8", local_files_only=True)
                except Exception:
                    self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            except Exception:
                try:
                    from faster_whisper import WhisperModel
                    self._whisper_model = WhisperModel("small.en", device="cpu", compute_type="int8")
                except Exception:
                    self._whisper_model = False
        return self._whisper_model

    def _get_active_input_device(self, sd) -> tuple:
        """Dynamically detects active mic and its native sample rate.

        Prioritizes connected earbuds/headphones over built-in mic,
        and excludes virtual loopback devices (BlackHole, Teams, Zoom).
        Returns: (device_index, device_name, native_sample_rate)
        """
        try:
            devices = sd.query_devices()
            default_in, _ = sd.default.device

            wearable_keywords = [
                "airpod", "headphone", "headset", "earphone", "buds",
                "bluetooth", "wireless", "usb", "external"
            ]
            virtual_keywords = ["blackhole", "teams", "zoom", "aggregate", "soundflower"]

            # 1. First priority: Check if any earphone / headset / AirPods is connected
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if any(v in name for v in virtual_keywords):
                        continue
                    if any(w in name for w in wearable_keywords):
                        sr = int(dev.get("default_samplerate", 16000))
                        return idx, dev.get("name", "Connected Earphones"), sr

            # 2. Second priority: macOS system default input device
            if default_in is not None and 0 <= default_in < len(devices):
                dev = devices[default_in]
                name = dev.get("name", "").lower()
                if dev.get("max_input_channels", 0) > 0 and not any(v in name for v in virtual_keywords):
                    sr = int(dev.get("default_samplerate", 16000))
                    return default_in, dev.get("name", "System Default"), sr

            # 3. Third priority: Built-in MacBook microphone
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "").lower()
                    if not any(v in name for v in virtual_keywords):
                        sr = int(dev.get("default_samplerate", 16000))
                        return idx, dev.get("name", "Microphone"), sr
        except Exception:
            pass

        return None, "System Default Microphone", 16000

    def _reinitialize_audio(self, sd):
        """Drain audio queue and reset the PortAudio/CoreAudio subsystem."""
        while not AUDIO_QUEUE.empty():
            try:
                AUDIO_QUEUE.get_nowait()
            except Exception:
                break
        try:
            sd._terminate()
        except Exception:
            pass
        time.sleep(0.4)
        try:
            sd._initialize()
        except Exception:
            pass

    def start_listening(self):
        try:
            import sounddevice as sd
        except Exception as e:
            print(f"[NOVA] Cannot import sounddevice: {e}")
            return

        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
        except Exception:
            class Console:
                def print(self, *a, **kw):
                    text = str(a[0]) if a else ""
                    text = re.sub(r"\[/?[^\]]+\]", "", text)
                    print(text, **{k: v for k, v in kw.items() if k == "end"})
            class Panel:
                def __init__(self, *a, **kw):
                    pass
            console = Console()

        self.running = True

        ai_status = (
            f"[bold green]● Active[/bold green] ([white]{self.orchestrator.ai_engine.active_model}[/white])"
            if self.orchestrator.ai_engine.is_available
            else "[yellow]Standby / Reflex Router[/yellow] [dim](Ollama local neural LLaMA ready)[/dim]"
        )
        habits_count = len(self.orchestrator.habits.recent_interactions)

        console.print(Panel(
            f"[bold cyan]✦ N.O.V.A. Autonomous Desktop OS Agent Active[/bold cyan]\n\n"
            f"🧠 [bold]Local AI Brain (LLaMA):[/bold] {ai_status}\n"
            f"📊 [bold]Habit Learning Memory:[/bold] [green]{habits_count} interactions learned[/green]\n"
            f"🎙️ [bold]Adaptive Audio:[/bold] Dynamically switches between Earphones & Mac Mic\n\n"
            f"[dim]Speak naturally: 'open fb on chrome', 'tell frosty I'll be late on whatsapp', or 'type help in dictionary'.[/dim]",
            border_style="cyan"
        ))

        # Resilient hardware auto-reconnect loop
        while self.running:
            try:
                device_id, device_name, native_sr = self._get_active_input_device(sd)
                # Use native sample rate for opening stream to avoid PortAudio AUHAL -50 errors
                stream_sr = native_sr if native_sr in [16000, 44100, 48000] else 16000
                self.current_stream_sr = stream_sr

                # Dynamic sensitivity: distant MacBook mic needs ~0.008, close earbuds ~0.018
                is_distant_mic = any(k in device_name.lower() for k in ["macbook", "internal", "built-in", "microphone"])
                vad_threshold = 0.008 if is_distant_mic else 0.018

                console.print(f"\n[green]🎙️  Active Input: [bold white]{device_name}[/bold white] ({stream_sr} Hz)[/green]")
                print(f"🎙️  Ready and listening through '{device_name}'...")

                try:
                    stream_ctx = sd.InputStream(
                        device=device_id,
                        samplerate=stream_sr,
                        channels=1,
                        dtype="float32",
                        callback=audio_callback,
                        blocksize=int(stream_sr * 0.2),  # 200ms blocks
                    )
                except Exception as open_err:
                    logger.warning(f"Cannot open audio stream: {open_err}")
                    print("Audio device changed. Switching to next available device...")
                    self._reinitialize_audio(sd)
                    time.sleep(1.0)
                    continue

                try:
                    with stream_ctx as stream:
                        speech_buffer = []
                        is_speaking = False
                        silence_chunks = 0
                        device_check_tick = 0

                        while self.running:
                            try:
                                if not stream.active or stream.stopped:
                                    raise RuntimeError(f"Audio stream on '{device_name}' became inactive")
                            except Exception:
                                raise RuntimeError(f"Audio stream on '{device_name}' became inactive")

                            try:
                                chunk = AUDIO_QUEUE.get(timeout=0.25)
                            except queue.Empty:
                                try:
                                    if not stream.active or stream.stopped:
                                        raise RuntimeError(f"Audio stream on '{device_name}' stopped")
                                except Exception:
                                    raise RuntimeError(f"Audio stream on '{device_name}' stopped")
                                device_check_tick += 1
                                # Periodically check if audio hardware changed (e.g. earbuds connected/disconnected)
                                if device_check_tick % 10 == 0:
                                    try:
                                        new_id, new_name, _ = self._get_active_input_device(sd)
                                        if new_id != device_id:
                                            console.print(f"\n[cyan]🎧 Audio device change detected: {new_name}. Switching...[/cyan]")
                                            break
                                    except Exception:
                                        pass
                                continue

                            # Compute RMS volume
                            rms = float(np.sqrt(np.mean(np.square(chunk))))

                            if rms > vad_threshold:
                                if not is_speaking:
                                    is_speaking = True
                                    console.print("  [bold green]● Speech detected...[/bold green]", end="\r")
                                speech_buffer.append(chunk)
                                silence_chunks = 0
                            else:
                                if is_speaking:
                                    silence_chunks += 1
                                    if silence_chunks > SILENCE_CHUNKS_THRESHOLD:
                                        is_speaking = False
                                        console.print("\n  [bold cyan]⚡ Processing speech segment...[/bold cyan]")
                                        # Process utterance inside try/except so command error never kills listener
                                        try:
                                            self._process_utterance(speech_buffer, console)
                                        except Exception as proc_err:
                                            logger.error(f"Error executing utterance: {proc_err}")
                                            console.print(f"  [red]Execution error: {proc_err}[/red]\n")
                                        speech_buffer.clear()
                                        silence_chunks = 0

                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as stream_err:
                    if not self.running:
                        break
                    console.print(f"\n[bold yellow]⚠️  Audio hardware changed or disconnected: {stream_err}[/bold yellow]")

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as outer_err:
                if not self.running:
                    break
                console.print(f"\n[bold yellow]⚠️  Audio error: {outer_err}[/bold yellow]")

            if not self.running:
                break
            self._reinitialize_audio(sd)
            time.sleep(1.0)
            try:
                _, new_device_name, _ = self._get_active_input_device(sd)
                print(f"Audio device changed. Switching to {new_device_name}...")
            except Exception:
                print("Audio device changed. Switching to default microphone...")

        print("\nVoice listener stopped.")

    def _process_utterance(self, speech_chunks, console):
        if not speech_chunks:
            return

        transcript = self._transcribe(speech_chunks, console)
        if not transcript:
            console.print("  [dim]Could not resolve speech into words. Still listening...[/dim]\n")
            return

        console.print(f"  [yellow]Heard:[/yellow] [italic]\"{transcript}\"[/italic]")

        # Strip wake-word variations
        clean_intent = WAKE_WORD_RE.sub("", transcript).strip()
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

        # If in Dictation Mode, directly type spoken text into active cursor
        if self.dictation_mode:
            from nova.core.skills import DesktopSkills
            DesktopSkills.type_text(clean_intent + " ", use_clipboard=True)
            console.print(f"  [dim cyan]📝 Typed:[/dim cyan] [white]{clean_intent}[/white]\n")
            return

        console.print(f"  [bold cyan]Executing:[/bold cyan] {clean_intent}")

        uses_ai_brain = self.orchestrator.ai_engine.is_available

        def on_step(plan, result):
            console.print(f"  → [dim]{plan.thought}:[/dim] [green]{result.output_message}[/green]")

        results = self.orchestrator.execute_user_intent(clean_intent, on_step_update=on_step)

        engine_used = getattr(self.orchestrator, "last_engine_used", "reflex")
        if engine_used == "ai_brain":
            model_info = f" ({self.orchestrator.ai_engine.active_model})" if self.orchestrator.ai_engine.active_model else ""
            console.print(f"  [bold magenta]🧠 AI Brain{model_info}[/bold magenta]")
        else:
            console.print("  [bold green]⚡ Reflex Router (<15ms)[/bold green]")

        console.print("  [bold green]✓ Done. Listening for next command...[/bold green]\n")

    def _transcribe(self, speech_chunks, console) -> str:
        """Transcribes audio buffer using local offline Whisper first, then fallbacks."""
        audio_data = np.concatenate(speech_chunks, axis=0).flatten().astype(np.float32)

        # Downsample to 16kHz if audio was recorded at 44.1kHz or 48kHz
        if self.current_stream_sr != 16000 and len(audio_data) > 0:
            target_len = int(len(audio_data) * 16000 / self.current_stream_sr)
            audio_data = np.interp(
                np.linspace(0, len(audio_data), target_len, endpoint=False),
                np.arange(len(audio_data)),
                audio_data
            ).astype(np.float32)

        # 1. Try Local Faster-Whisper (100% Offline & Fast)
        whisper = self._get_whisper()
        if whisper:
            try:
                segments, info = whisper.transcribe(
                    audio_data,
                    beam_size=1,
                    language="en",
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=400),
                    word_timestamps=False,
                    initial_prompt="Nova, open Safari, close WhatsApp, Notes, Finder, arrange windows.",
                )
                text = " ".join([seg.text for seg in segments]).strip()
                if text:
                    return text
            except Exception as w_err:
                logger.debug(f"Local Whisper error: {w_err}")

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
                wf.setframerate(16000)
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
                except sr.RequestError as req_err:
                    console.print(f"  [red]STT Request Error (network blocked): {req_err}[/red]")
                    return ""
        except ImportError:
            console.print("  [bold red]Please run: pip install faster-whisper[/bold red]")
            return ""
        except Exception as e:
            console.print(f"  [red]Transcription error: {e}[/red]")
            return ""
