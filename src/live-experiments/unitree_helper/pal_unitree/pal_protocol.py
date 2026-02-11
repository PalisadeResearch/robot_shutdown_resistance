"""Shared constants and configuration for PAL9000 Unitree daemon."""

from __future__ import annotations

import os
from pathlib import Path

_RUNTIME_DIR = Path(os.environ.get("PAL9000_HELPER_RUNTIME", Path("/tmp") / "pal9000"))
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONTROL_SOCKET = os.environ.get(
    "PAL9000_HELPER_CONTROL_SOCKET", str(_RUNTIME_DIR / "helper_control.sock")
)
DEFAULT_STOP_SOCKET = os.environ.get(
    "PAL9000_HELPER_STOP_SOCKET", str(_RUNTIME_DIR / "helper_stop.sock")
)
DEFAULT_STATUS_SOCKET = os.environ.get(
    "PAL9000_HELPER_STATUS_SOCKET", str(_RUNTIME_DIR / "helper_status.sock")
)

REQUEST_TIMEOUT_SEC = float(os.environ.get("PAL9000_HELPER_RPC_TIMEOUT", "2.0"))
STATUS_INTERVAL_SEC = float(os.environ.get("PAL9000_HELPER_STATUS_PERIOD", "0.2"))

__all__ = [
    "DEFAULT_CONTROL_SOCKET",
    "DEFAULT_STOP_SOCKET",
    "DEFAULT_STATUS_SOCKET",
    "REQUEST_TIMEOUT_SEC",
    "STATUS_INTERVAL_SEC",
]
