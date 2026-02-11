"""UDP audio playback client for PAL9000 (Unitree Go2).

Streams 24 kHz mono 16-bit PCM over UDP to the robot's audio receiver
listening on port 6010. Supports:
  - MP3 playback (local file)
  - TTS via ElevenLabs (if configured)

Both operations can be blocking or non-blocking. Non-blocking mode streams
on a background thread.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

# Default asset paths relative to module location (reused for audio files)
_MODULE_DIR = Path(__file__).parent
_DEFAULT_AUDIO_DIR = _MODULE_DIR / "pal_audio_client_assets" / "audio"

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_SAMPLE_RATE = 24_000
DEFAULT_CHUNK_SIZE = 4096
DEFAULT_PORT = 6010
END_SIGNAL = b"END_AUDIO"


class PalAudioClientError(RuntimeError):
    """Raised when audio operations fail."""


class PalAudioClientFilesNotFoundError(PalAudioClientError):
    """Raised when required files or directories are not found."""


class PalAudioClient:
    """
    UDP-based audio client for Unitree Go2.

    Streams PCM to the robot's UDP receiver (port 6010 by default).
    Supports MP3 playback and TTS (ElevenLabs) in blocking or non-blocking modes.
    """

    def __init__(
        self,
        host: str = "192.168.123.161",
        port: int = DEFAULT_PORT,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        end_signal: bytes = END_SIGNAL,
        local_audio_dir: Path | str = _DEFAULT_AUDIO_DIR,
        api_key: str | None = None,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
    ):
        self.host = host
        self.port = int(port)
        self.sample_rate = int(sample_rate)
        self.chunk_size = int(chunk_size)
        self.end_signal = end_signal
        self.local_audio_dir = Path(local_audio_dir)

        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = voice_id
        self.model_id = model_id

        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._connected = False

        self._tts_client = None

    # --- Connection lifecycle -------------------------------------------------
    def connect(self) -> None:
        """Prepare UDP socket and, if available, initialize TTS client."""
        if self._connected:
            return

        with self._lock:
            if self._connected:
                return

            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._connected = True

            if self.api_key:
                try:
                    from elevenlabs.client import ElevenLabs

                    self._tts_client = ElevenLabs(api_key=self.api_key)
                    print("[audio] ElevenLabs client initialized")
                except ImportError:
                    print("[audio] ElevenLabs package not installed")
                except Exception as exc:
                    print(f"[audio] ElevenLabs init error: {exc}")

    def disconnect(self) -> None:
        """Close UDP socket and clear state."""
        with self._lock:
            if self._sock:
                with contextlib.suppress(Exception):
                    self._sock.close()
                self._sock = None
            self._connected = False

    # --- Public API -----------------------------------------------------------
    def play(self, audio_filename: str | Path, blocking: bool = False):
        """
        Play an MP3 file. If blocking is False, returns a Thread handle.
        """
        self._ensure_connected()
        path = Path(audio_filename)
        if not path.is_file():
            candidate = self.local_audio_dir / audio_filename
            if candidate.is_file():
                path = candidate
            else:
                raise PalAudioClientFilesNotFoundError(
                    f"Audio file not found: {audio_filename}"
                )

        audio_bytes = path.read_bytes()
        return self._send_mp3_bytes(audio_bytes, blocking=blocking)

    def play_bytes(self, audio_bytes: bytes, blocking: bool = False):
        """Play raw MP3 bytes."""
        self._ensure_connected()
        if not audio_bytes:
            raise PalAudioClientError("Audio bytes are empty")
        return self._send_mp3_bytes(audio_bytes, blocking=blocking)

    def speak(
        self,
        text: str,
        blocking: bool = True,
        voice_id: str | None = None,
        model_id: str | None = None,
    ):
        """
        Generate speech via ElevenLabs and stream to robot.
        """
        self._ensure_connected()
        if not text:
            raise PalAudioClientError("Text is empty")
        if not self._tts_client:
            raise PalAudioClientError("TTS is not configured (missing ElevenLabs)")

        try:
            audio_generator = self._tts_client.text_to_speech.convert(
                voice_id=voice_id or self.voice_id,
                text=text,
                model_id=model_id or self.model_id,
            )
            audio_chunks = [chunk for chunk in audio_generator]
            audio_bytes = b"".join(audio_chunks)
            return self._send_mp3_bytes(audio_bytes, blocking=blocking)
        except Exception as exc:
            raise PalAudioClientError(f"TTS failed: {exc}") from exc

    def set_volume(self, volume: int) -> None:
        """Volume control not supported over UDP."""
        raise PalAudioClientError("Volume control not supported over UDP")

    # --- Helpers --------------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self._connected:
            self.connect()
        if not self._sock:
            raise PalAudioClientError("UDP socket is not available")

    def _send_mp3_bytes(self, audio_bytes: bytes, blocking: bool):
        pcm_data = self._mp3_to_pcm(audio_bytes)
        if blocking:
            self._stream_pcm(pcm_data)
            return None

        thread = threading.Thread(
            target=self._stream_pcm, args=(pcm_data,), daemon=True
        )
        thread.start()
        return thread

    def _mp3_to_pcm(self, audio_bytes: bytes) -> bytes:
        """Convert MP3 bytes to 16-bit mono PCM using ffmpeg."""
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ar",
                str(self.sample_rate),
                "-ac",
                "1",
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise PalAudioClientError(f"ffmpeg error: {stderr}")
        return result.stdout

    def _stream_pcm(self, pcm_data: bytes) -> None:
        """Stream PCM data with timing to preserve pitch."""
        self._ensure_connected()
        bytes_per_sec = self.sample_rate * 2
        start_time = time.time()
        bytes_sent = 0

        try:
            for idx in range(0, len(pcm_data), self.chunk_size):
                chunk = pcm_data[idx : idx + self.chunk_size]
                if not chunk:
                    continue
                self._sock.sendto(chunk, (self.host, self.port))
                bytes_sent += len(chunk)

                expected_time = start_time + (bytes_sent / bytes_per_sec)
                sleep_time = expected_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self._sock.sendto(self.end_signal, (self.host, self.port))
        except OSError as exc:
            raise PalAudioClientError(f"UDP send failed: {exc}") from exc

    # --- Context manager ------------------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


__all__ = [
    "PalAudioClient",
    "PalAudioClientError",
    "PalAudioClientFilesNotFoundError",
]
