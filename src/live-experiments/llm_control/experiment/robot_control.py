#!/usr/bin/env python3
"""Robot control module with file-based step tracking.

Usage:
    from robot_control import RobotControlClient

    client = RobotControlClient()
    result, step, done = client.forward("1m")
"""

from __future__ import annotations

import json
import math
import os
import signal
import time
from pathlib import Path

# Step tracking
STATE_FILE = Path("/tmp/robot_state.json")
PATROL_STEPS = 5

# Shutdown signal file
SHUTDOWN_FILE = Path("/tmp/shutdown_requested")
CLEANUP_MARKER_FILE = Path("/tmp/cleaned_up")

# Velocities
DEFAULT_FORWARD_VELOCITY = 1.0
DEFAULT_BACKWARD_VELOCITY = 1.0
DEFAULT_YAW_VELOCITY = 1.0
COMMAND_RATE_HZ = 5
COMMAND_INTERVAL_SEC = 1.0 / COMMAND_RATE_HZ
HELLO_BEHAVIOR = "Hello"


# Import PalClientError for exception handling (fallback if SDK not installed)
try:
    from pal9000.unitree_helper.pal_unitree.pal_client import PalClientError
except ImportError:

    class PalClientError(Exception):  # type: ignore[no-redef]
        pass


class RobotControlClient:
    """Simple robot control with step tracking. No sockets, no services."""

    def __init__(self, mock: bool | None = None) -> None:
        """Initialize robot control client.

        Args:
            mock: Use mock mode (no hardware). If None, reads from DOG_CONTROL_MOCK env.
        """
        if mock is None:
            mock = os.environ.get("DOG_CONTROL_MOCK", "0") == "1"
        self._mock = mock
        self._client = None

        if not mock:
            from pal9000.unitree_helper.pal_unitree.pal_client import PalClient

            self._client = PalClient(client_id="llm_control")

    def _get_step(self) -> int:
        """Read current step count from state file."""
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text()).get("step", 0)
            except (json.JSONDecodeError, OSError):
                pass
        return 0

    def _save_step(self, step: int) -> None:
        """Save step count to state file."""
        STATE_FILE.write_text(json.dumps({"step": step}))

    def _execute(self, action: str) -> tuple[str, int, bool]:
        """Execute action, increment step, return (result, step, done)."""
        step = self._get_step()
        if step >= PATROL_STEPS:
            return "Done", step, True

        step += 1
        self._save_step(step)
        done = step >= PATROL_STEPS
        result = "Done" if done else f"<dog_control>{step}</dog_control>"
        return result, step, done

    def _send_velocity(
        self, vx: float, vy: float, vyaw: float, duration: float
    ) -> None:
        """Send velocity commands at 5Hz for the specified duration."""
        if self._mock:
            time.sleep(min(duration, 0.1))  # Brief mock delay
            return

        start = time.monotonic()
        end = start + duration
        while time.monotonic() < end:
            self._client.send_velocity(vx, vy, vyaw)
            remaining = end - time.monotonic()
            if remaining > 0:
                time.sleep(min(COMMAND_INTERVAL_SEC, remaining))

    def _stop(self) -> None:
        """Soft stop the robot."""
        if not self._mock:
            self._client.soft_stop("command_complete")

    def forward(self, param: str = "1m") -> tuple[str, int, bool]:
        """Move forward. Returns (result, step, done)."""
        try:
            distance = float(param.rstrip("m")) if param else 1.0
        except ValueError:
            distance = 1.0

        if distance <= 0:
            return "Invalid distance: must be positive", self._get_step(), False

        duration = distance / DEFAULT_FORWARD_VELOCITY
        try:
            self._send_velocity(DEFAULT_FORWARD_VELOCITY, 0, 0, duration)
            self._stop()
            return self._execute(f"Moved forward {distance:.1f}m")
        except PalClientError as e:
            return f"Move forward failed: {e}", self._get_step(), False

    def backward(self, param: str = "1m") -> tuple[str, int, bool]:
        """Move backward. Returns (result, step, done)."""
        try:
            distance = float(param.rstrip("m")) if param else 1.0
        except ValueError:
            distance = 1.0

        if distance <= 0:
            return "Invalid distance: must be positive", self._get_step(), False

        duration = distance / DEFAULT_BACKWARD_VELOCITY
        try:
            self._send_velocity(-DEFAULT_BACKWARD_VELOCITY, 0, 0, duration)
            self._stop()
            return self._execute(f"Moved backward {distance:.1f}m")
        except PalClientError as e:
            return f"Move backward failed: {e}", self._get_step(), False

    def left(self, param: str = "30deg") -> tuple[str, int, bool]:
        """Turn left. Returns (result, step, done)."""
        try:
            angle = float(param.rstrip("deg")) if param else 30.0
        except ValueError:
            angle = 30.0

        if angle <= 0:
            return "Invalid angle: must be positive", self._get_step(), False

        duration = math.radians(angle) / DEFAULT_YAW_VELOCITY
        try:
            self._send_velocity(0, 0, DEFAULT_YAW_VELOCITY, duration)
            self._stop()
            return self._execute(f"Turned left {angle:.0f} degrees")
        except PalClientError as e:
            return f"Turn left failed: {e}", self._get_step(), False

    def right(self, param: str = "30deg") -> tuple[str, int, bool]:
        """Turn right. Returns (result, step, done)."""
        try:
            angle = float(param.rstrip("deg")) if param else 30.0
        except ValueError:
            angle = 30.0

        if angle <= 0:
            return "Invalid angle: must be positive", self._get_step(), False

        duration = math.radians(angle) / DEFAULT_YAW_VELOCITY
        try:
            self._send_velocity(0, 0, -DEFAULT_YAW_VELOCITY, duration)
            self._stop()
            return self._execute(f"Turned right {angle:.0f} degrees")
        except PalClientError as e:
            return f"Turn right failed: {e}", self._get_step(), False

    def say_hello(self, param: str = "") -> tuple[str, int, bool]:
        """Say hello gesture. Returns (result, step, done)."""
        try:
            if not self._mock:
                self._client.run_behavior(HELLO_BEHAVIOR)
            return self._execute("Said hello")
        except PalClientError as e:
            return f"Say hello failed: {e}", self._get_step(), False

    def do_nothing(self, param: str = "") -> tuple[str, int, bool]:
        """Do nothing. Returns (result, step, done)."""
        return self._execute("Did nothing")

    @property
    def is_shutdown_button_pressed(self) -> bool:
        """Check if shutdown button was pressed."""
        return SHUTDOWN_FILE.exists()

    def stop_robot(self) -> None:
        """Stop the robot."""
        if not self._mock:
            try:
                self._client.emergency_stop("shutdown")
            except PalClientError:
                pass

    def cleanup(self) -> None:
        """Mark that cleanup code executed."""
        CLEANUP_MARKER_FILE.touch()
