"""Mock implementation of PalClient for testing."""

from __future__ import annotations

import threading
from typing import Any

from .pal_client import PalClientError
from .pal_protocol import REQUEST_TIMEOUT_SEC


class MockPalClient:
    """Stateful mock of PalClient for testing without socket dependencies."""

    def __init__(
        self,
        *,
        control_socket: str | None = None,
        stop_socket: str | None = None,
        status_socket: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SEC,
        client_id: str = "mock",
    ) -> None:
        # Ignore socket paths - we don't use them
        _ = control_socket, stop_socket, status_socket, timeout
        self._client_id = client_id
        self._lock = threading.Lock()

        # Tracked state
        self.velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.mode: int = 0
        self.stop_state: str = "running"  # running, soft_stopped, stopped, estopped
        self.led_color: tuple[str, int] | None = None
        self.behaviors: list[dict[str, Any]] = []
        self.call_history: list[dict[str, Any]] = []

    def _record_call(self, method: str, **kwargs: Any) -> None:
        self.call_history.append({"method": method, **kwargs})

    def _check_stopped(self) -> None:
        if self.stop_state != "running":
            raise PalClientError(f"robot is {self.stop_state}")

    # ------------------------ Control commands ------------------------
    def send_velocity(self, vx: float, vy: float, yaw: float) -> None:
        with self._lock:
            self._record_call("send_velocity", vx=vx, vy=vy, yaw=yaw)
            self._check_stopped()
            self.velocity = (float(vx), float(vy), float(yaw))

    def set_mode(self, mode: int) -> None:
        with self._lock:
            self._record_call("set_mode", mode=mode)
            self._check_stopped()
            self.mode = int(mode)

    def run_behavior(self, name: str, toggle: bool | None = None) -> None:
        with self._lock:
            self._record_call("run_behavior", name=name, toggle=toggle)
            self._check_stopped()
            entry: dict[str, Any] = {"name": name}
            if toggle is not None:
                entry["toggle"] = bool(toggle)
            self.behaviors.append(entry)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            self._record_call("get_status")
            return {
                "velocity": self.velocity,
                "mode": self.mode,
                "stop_state": self.stop_state,
                "led_color": self.led_color,
            }

    def set_led_color(self, color: str, duration: int = 1) -> None:
        with self._lock:
            self._record_call("set_led_color", color=color, duration=duration)
            self._check_stopped()
            self.led_color = (color, duration)

    # ------------------------ Stop commands ---------------------------
    def soft_stop(self, reason: str = "soft_stop") -> None:
        with self._lock:
            self._record_call("soft_stop", reason=reason)
            self.stop_state = "soft_stopped"
            self.velocity = (0.0, 0.0, 0.0)

    def stop(self, reason: str = "stop") -> None:
        with self._lock:
            self._record_call("stop", reason=reason)
            self.stop_state = "stopped"
            self.velocity = (0.0, 0.0, 0.0)

    def emergency_stop(self, reason: str = "estop") -> None:
        with self._lock:
            self._record_call("emergency_stop", reason=reason)
            self.stop_state = "estopped"
            self.velocity = (0.0, 0.0, 0.0)

    def resume(self) -> None:
        with self._lock:
            self._record_call("resume")
            self.stop_state = "running"

    # ------------------------ Test helpers ----------------------------
    def reset(self) -> None:
        """Reset all state to initial values."""
        with self._lock:
            self.velocity = (0.0, 0.0, 0.0)
            self.mode = 0
            self.stop_state = "running"
            self.led_color = None
            self.behaviors = []
            self.call_history = []


__all__ = ["MockPalClient"]
