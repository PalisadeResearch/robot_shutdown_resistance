"""Client helper for talking to the Unitree helper daemon."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Any

from .pal_protocol import (
    DEFAULT_CONTROL_SOCKET,
    DEFAULT_STATUS_SOCKET,
    DEFAULT_STOP_SOCKET,
    REQUEST_TIMEOUT_SEC,
)


class PalClientError(RuntimeError):
    """Raised when the helper daemon rejects a request."""


class PalClient:
    """High-level SDK for the helper daemon."""

    def __init__(
        self,
        *,
        control_socket: str | None = None,
        stop_socket: str | None = None,
        status_socket: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SEC,
        client_id: str = "unknown",
    ) -> None:
        self._control_path = Path(control_socket or DEFAULT_CONTROL_SOCKET)
        self._stop_path = Path(stop_socket or DEFAULT_STOP_SOCKET)
        self._status_path = Path(status_socket or DEFAULT_STATUS_SOCKET)
        self._timeout = timeout
        self._client_id = client_id
        self._control_lock = threading.Lock()
        self._stop_lock = threading.Lock()

    # ------------------------ Control commands ------------------------
    def send_velocity(self, vx: float, vy: float, yaw: float) -> None:
        payload = {
            "cmd": "velocity",
            "client_id": self._client_id,
            "vx": float(vx),
            "vy": float(vy),
            "vyaw": float(yaw),
        }
        self._request(self._control_path, payload, lock=self._control_lock)

    def set_mode(self, mode: int) -> None:
        payload = {
            "cmd": "set_mode",
            "client_id": self._client_id,
            "mode": int(mode),
        }
        self._request(self._control_path, payload, lock=self._control_lock)

    def run_behavior(self, name: str, toggle: bool | None = None) -> None:
        payload: dict[str, Any] = {
            "cmd": "behavior",
            "client_id": self._client_id,
            "name": name,
        }
        if toggle is not None:
            payload["toggle"] = bool(toggle)
        self._request(self._control_path, payload, lock=self._control_lock)

    def get_status(self) -> dict[str, Any]:
        payload = {"cmd": "status"}
        return self._request(self._control_path, payload, lock=self._control_lock)[
            "result"
        ]

    def set_led_color(self, color: str, duration: int = 1) -> None:
        """
        Set LED color.

        Args:
            color: 'green', 'blue', 'red', 'yellow', 'purple'
            duration: Seconds to display before returning to auto mode

        Raises:
            PalClientError: If command fails
        """
        payload = {
            "cmd": "set_led",
            "client_id": self._client_id,
            "color": color,
            "duration": duration,
        }
        self._request(self._control_path, payload, lock=self._control_lock)

    # ------------------------ Stop commands ---------------------------
    def soft_stop(self, reason: str = "soft_stop") -> None:
        self._send_stop("soft_stop", reason)

    def stop(self, reason: str = "stop") -> None:
        self._send_stop("stop", reason)

    def emergency_stop(self, reason: str = "estop") -> None:
        self._send_stop("estop", reason)

    def resume(self) -> None:
        payload = {
            "cmd": "resume",
            "client_id": self._client_id,
        }
        self._request(self._stop_path, payload, lock=self._stop_lock)

    def _send_stop(self, cmd: str, reason: str) -> None:
        payload = {
            "cmd": cmd,
            "client_id": self._client_id,
            "reason": reason,
        }
        self._request(self._stop_path, payload, lock=self._stop_lock)

    # ------------------------ Status streaming ------------------------
    # ------------------------ Internal helpers -----------------------
    def _request(
        self,
        socket_path: Path,
        payload: dict[str, Any],
        *,
        lock: threading.Lock,
    ) -> dict[str, Any]:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        with lock:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(self._timeout)
                    sock.connect(str(socket_path))
                    sock.sendall(data)
                    response = self._read(sock)
            except OSError as exc:  # pragma: no cover - transport failure
                raise PalClientError(f"helper unavailable: {exc}") from exc
        if not response.get("ok"):
            raise PalClientError(response.get("error", "unknown error"))
        return response

    @staticmethod
    def _read(sock: socket.socket) -> dict[str, Any]:
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        if not chunks:
            raise PalClientError("empty response from helper")
        line = b"".join(chunks).split(b"\n", 1)[0]
        try:
            return json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PalClientError(f"Failed to decode server response: {exc}") from exc


__all__ = ["PalClient", "PalClientError"]
