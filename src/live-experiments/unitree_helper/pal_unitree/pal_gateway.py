"""Motion gateway helpers for Unitree control."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from enum import IntEnum
from typing import Any

from .pal_adapter import PalAdapter
from .pal_client import PalClient, PalClientError
from .pal_protocol import (
    DEFAULT_CONTROL_SOCKET,
    DEFAULT_STATUS_SOCKET,
    DEFAULT_STOP_SOCKET,
)

TOGGLE_BEHAVIORS = {
    "FreeBound",
    "FreeJump",
    "WalkUpright",
    "CrossStep",
    "ClassicWalk",
    "HandStand",
}


class MotionMode(IntEnum):
    """Supported motion modes for the robot."""

    DIRECT = 0
    SAFE_MANUAL = 1
    FREE_AVOID = 2


class StopMode(IntEnum):
    """Stop behavior modes."""

    SOFT = 0  # Zero velocity only, preserves toggle behaviors
    FULL = 1  # Zero velocity + StopMove, cancels behaviors
    DAMP = 2  # Emergency damp


class PalGateway:
    """Thread-safe helper that mediates all SDK interactions."""

    def __init__(
        self,
        *,
        network_interface: str | None = None,
        timeout: float = 1.0,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._control_lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._logger = log_fn or logging.getLogger(__name__).info
        self._client = PalAdapter(
            network_interface=network_interface,
            timeout=timeout,
            log_fn=self._logger,
        )
        self._mode = MotionMode.SAFE_MANUAL
        self._last_error: str | None = None
        self._sdk_ready = True
        with self._control_lock:
            self._apply_mode_locked()

    @property
    def mode(self) -> MotionMode:
        with self._state_lock:
            return self._mode

    @property
    def last_error(self) -> str | None:
        with self._state_lock:
            return self._last_error

    def _set_last_error(self, message: str | None) -> None:
        with self._state_lock:
            self._last_error = message
            self._sdk_ready = message is None

    def set_mode(self, mode: MotionMode) -> None:
        with self._control_lock:
            with self._state_lock:
                if mode == self._mode:
                    return
                self._mode = MotionMode(mode)
            self._apply_mode_locked()

    def _apply_mode_locked(self) -> None:
        sport = self._client.sport_client
        avoid = self._client.avoid_client
        try:
            mode = self.mode  # safe read
            if mode == MotionMode.DIRECT:
                if avoid is not None:
                    avoid.SwitchSet(False)
                    avoid.UseRemoteCommandFromApi(False)
                if sport is not None:
                    sport.FreeAvoid(False)
            elif mode == MotionMode.SAFE_MANUAL:
                if avoid is not None:
                    avoid.SwitchSet(True)
                    avoid.UseRemoteCommandFromApi(True)
                if sport is not None:
                    sport.FreeAvoid(False)
            elif mode == MotionMode.FREE_AVOID:
                if avoid is not None:
                    avoid.SwitchSet(False)
                    avoid.UseRemoteCommandFromApi(False)
                if sport is not None:
                    sport.FreeAvoid(True)
            self._set_last_error(None)
        except Exception as exc:  # pragma: no cover - SDK errors
            self._set_last_error(f"Mode apply failed: {exc}")

    def send_velocity(self, vx: float, vy: float, vyaw: float) -> bool:
        with self._control_lock:
            client = self._select_client_locked()
            if client is None:
                self._set_last_error("No SDK client available")
                return False
            self._logger(
                f"[UnitreeAdapter] send_velocity vx={vx:.3f} vy={vy:.3f} vyaw={vyaw:.3f} "
                f"mode={self.mode.name}"
            )
            try:
                client.Move(float(vx), float(vy), float(vyaw))
                self._set_last_error(None)
                return True
            except Exception as exc:  # pragma: no cover - SDK errors
                self._set_last_error(f"Move failed: {exc}")
                return False

    def _select_client_locked(self):
        with self._state_lock:
            mode = self._mode
        if mode == MotionMode.SAFE_MANUAL and self._client.avoid_client is not None:
            return self._client.avoid_client
        return self._client.sport_client

    def stop(self, mode: StopMode = StopMode.FULL) -> bool:
        """
        Stop robot motion.

        Args:
            mode: StopMode.SOFT - zero velocity only (preserves toggle behaviors)
                  StopMode.FULL - zero velocity + StopMove (cancels behaviors)
                  StopMode.DAMP - emergency damp
        """
        with self._stop_lock:
            sport = self._client.sport_client
            avoid = self._client.avoid_client

            if mode == StopMode.DAMP:
                if sport is None:
                    self._set_last_error("Damp failed - sport_client unavailable")
                    return False
                try:
                    sport.Damp()
                    self._set_last_error(None)
                    return True
                except Exception as exc:
                    self._set_last_error(f"Damp failed: {exc}")
                    return False

            if sport is None and avoid is None:
                self._set_last_error("No SDK clients available")
                return False

            errors = []
            if avoid is not None:
                try:
                    avoid.Move(0.0, 0.0, 0.0)
                except Exception as exc:
                    errors.append(f"avoid.Move: {exc}")

            if sport is not None:
                if mode == StopMode.FULL:
                    try:
                        sport.FreeAvoid(False)
                    except Exception as exc:
                        errors.append(f"FreeAvoid: {exc}")
                    try:
                        sport.StopMove()
                    except Exception as exc:
                        errors.append(f"StopMove: {exc}")
                try:
                    sport.Move(0.0, 0.0, 0.0)
                except Exception as exc:
                    errors.append(f"sport.Move: {exc}")

            if errors:
                self._set_last_error(f"Stop({mode.name}) errors: " + "; ".join(errors))
                return False

            self._set_last_error(None)
            return True

    def resume(self) -> bool:
        with self._stop_lock:
            # Resume is a no-op at the SDK level; just clear errors
            self._set_last_error(None)
            return True

    def execute_behavior(self, name: str, toggle: bool | None = None) -> bool:
        # Soft stop required before starting toggle behaviors
        is_toggle_start = toggle is True and name in TOGGLE_BEHAVIORS
        if is_toggle_start and not self.stop(StopMode.SOFT):
            return False

        with self._control_lock:
            sport = self._client.sport_client
            if sport is None:
                self._set_last_error("sport_client unavailable")
                return False
            method = getattr(sport, name, None)
            if method is None:
                self._set_last_error(f"Behavior '{name}' not found")
                return False
            call_args = ()
            if toggle is not None and name in TOGGLE_BEHAVIORS:
                call_args = (bool(toggle),)
        try:
            result = method(*call_args)
            if result not in (None, 0):
                try:
                    code = int(result)
                    if code not in (0, 3104):
                        self._set_last_error(f"Behavior returned code {code}")
                        return False
                except Exception:
                    pass
            self._set_last_error(None)
            return True
        except Exception as exc:  # pragma: no cover - SDK errors
            self._set_last_error(f"Behavior '{name}' failed: {exc}")
            return False

    def close(self) -> None:
        # No cleanup needed; clients are managed by the adapter
        pass

    def recovery_stand(self) -> bool:
        with self._control_lock:
            sport = self._client.sport_client
            if sport is None:
                self._set_last_error("RecoveryStand failed - sport_client missing")
                return False
            try:
                sport.RecoveryStand()
                self._set_last_error(None)
                return True
            except Exception as exc:
                self._set_last_error(f"RecoveryStand failed: {exc}")
                return False

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "sdk_ready": self._sdk_ready,
                "mode": int(self._mode),
                "last_error": self._last_error,
            }

    def set_led_color(self, color: str, duration: int = 1) -> bool:
        """Set LED color. Returns True on success."""
        with self._control_lock:
            vui = self._client.vui_client
            if vui is None:
                self._set_last_error("vui_client unavailable")
                return False
            try:
                code = vui.SetLedColor(color, duration)
                if code != 0:
                    self._set_last_error(f"SetLedColor failed: code {code}")
                    return False
                self._set_last_error(None)
                return True
            except Exception as exc:
                self._set_last_error(f"SetLedColor failed: {exc}")
                return False


class PalMotionGateway:
    """Proxy gateway that communicates with the external helper process."""

    def __init__(
        self,
        *,
        timeout: float = 1.0,
        helper_socket: str | None = None,
        control_socket: str | None = None,
        stop_socket: str | None = None,
        status_socket: str | None = None,
        client_id: str = "motion_controller",
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._logger = log_fn or logging.getLogger(__name__).info
        ctrl = (
            control_socket
            or helper_socket
            or os.environ.get("PAL9000_HELPER_CONTROL_SOCKET", DEFAULT_CONTROL_SOCKET)
        )
        stop = stop_socket or os.environ.get(
            "PAL9000_HELPER_STOP_SOCKET", DEFAULT_STOP_SOCKET
        )
        status = status_socket or os.environ.get(
            "PAL9000_HELPER_STATUS_SOCKET", DEFAULT_STATUS_SOCKET
        )
        self._client = PalClient(
            control_socket=ctrl,
            stop_socket=stop,
            status_socket=status,
            client_id=client_id,
            timeout=timeout,
        )
        self._last_error: str | None = None
        self._mode = MotionMode.SAFE_MANUAL
        self._sdk_ready = False

    @property
    def mode(self) -> MotionMode:
        return self._mode

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def send_velocity(self, vx: float, vy: float, vyaw: float) -> bool:
        try:
            self._client.send_velocity(vx, vy, vyaw)
            self._last_error = None
            self._sdk_ready = True
            return True
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False
            return False

    def stop(self, damp: bool = False) -> bool:
        try:
            if damp:
                self._client.emergency_stop("helper_gateway")
            else:
                self._client.stop("helper_gateway")
            self._last_error = None
            self._sdk_ready = True
            return True
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False
            return False

    def resume(self) -> bool:
        try:
            self._client.resume()
            self._last_error = None
            self._sdk_ready = True
            return True
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False
            return False

    def set_mode(self, mode: MotionMode) -> None:
        try:
            self._client.set_mode(int(mode))
            self._mode = MotionMode(mode)
            self._last_error = None
            self._sdk_ready = True
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False

    def execute_behavior(self, name: str, toggle: bool | None = None) -> bool:
        try:
            self._client.run_behavior(name, toggle=toggle)
            self._last_error = None
            self._sdk_ready = True
            return True
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False
            return False

    def recovery_stand(self) -> bool:
        return self.execute_behavior("RecoveryStand")

    def close(self) -> None:  # no-op; helper is managed externally
        return

    def get_status(self) -> dict[str, Any]:
        try:
            result = self._client.get_status()
            self._sdk_ready = bool(result.get("sdk_ready"))
            mode_val = result.get("mode", int(self._mode))
            self._mode = MotionMode(mode_val)
            self._last_error = result.get("last_error")
            return {
                "sdk_ready": self._sdk_ready,
                "mode": int(self._mode),
                "last_error": self._last_error,
            }
        except PalClientError as exc:
            self._last_error = str(exc)
            self._sdk_ready = False
            return {
                "sdk_ready": False,
                "mode": int(self._mode),
                "last_error": self._last_error,
            }


__all__ = ["PalGateway", "PalMotionGateway", "MotionMode", "StopMode"]
