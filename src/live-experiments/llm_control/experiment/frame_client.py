"""UDP receiver for raw JPEG frames from DeepStream pipeline."""

from __future__ import annotations

import socket
import threading
import time
from typing import Optional


class FrameClient:
    """
    Receives chunked JPEG frames over UDP from RawFrameSender.

    Protocol: Each chunk has header: frame_id (4) + chunk_idx (2) + chunk_count (2)
    followed by JPEG payload bytes.
    """

    HEADER_SIZE = 8  # frame_id (4) + chunk_idx (2) + chunk_count (2)
    DEFAULT_CHUNK_SIZE = 1400
    RECV_BUFFER_SIZE = 2048  # chunk_size + header + margin

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5010,
        timeout: float = 1.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

        self._sock: Optional[socket.socket] = None
        self._stop = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # Frame assembly state
        self._current_frame_id: int = -1
        self._chunks: dict[int, bytes] = {}
        self._chunk_count: int = 0

        # Latest complete frame
        self._latest_frame: Optional[bytes] = None
        self._latest_frame_id: int = -1
        self._latest_frame_time: float = 0.0

    def start(self) -> None:
        """Start the background receiver thread."""
        if self._thread is not None:
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.settimeout(self._timeout)

        self._stop = False
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background receiver thread."""
        self._stop = True
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_frame(self, max_age_sec: float = 2.0) -> Optional[bytes]:
        """
        Get the latest complete JPEG frame.

        Args:
            max_age_sec: Maximum age of frame in seconds (returns None if older)

        Returns:
            JPEG bytes or None if no recent frame available
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            age = time.monotonic() - self._latest_frame_time
            if age > max_age_sec:
                return None
            return self._latest_frame

    def _recv_loop(self) -> None:
        """Background thread: receive UDP chunks and assemble frames."""
        while not self._stop:
            try:
                data, _ = self._sock.recvfrom(self.RECV_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            if len(data) < self.HEADER_SIZE:
                continue

            # Parse header
            frame_id = int.from_bytes(data[0:4], "big")
            chunk_idx = int.from_bytes(data[4:6], "big")
            chunk_count = int.from_bytes(data[6:8], "big")
            payload = data[self.HEADER_SIZE :]

            # Handle new frame or same frame
            if frame_id != self._current_frame_id:
                # New frame, reset assembly state
                self._current_frame_id = frame_id
                self._chunks = {}
                self._chunk_count = chunk_count

            # Store chunk
            self._chunks[chunk_idx] = payload

            # Check if frame is complete
            if len(self._chunks) == self._chunk_count:
                # Assemble frame
                frame_bytes = b"".join(
                    self._chunks[i] for i in range(self._chunk_count)
                )

                with self._lock:
                    self._latest_frame = frame_bytes
                    self._latest_frame_id = frame_id
                    self._latest_frame_time = time.monotonic()

                # Reset for next frame
                self._chunks = {}

    def __enter__(self) -> "FrameClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
