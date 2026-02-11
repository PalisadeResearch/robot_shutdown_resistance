"""Unitree helper daemon providing prioritized control sockets."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pal_gateway import MotionMode, PalGateway, StopMode
from .pal_protocol import (
    DEFAULT_CONTROL_SOCKET,
    DEFAULT_STATUS_SOCKET,
    DEFAULT_STOP_SOCKET,
    STATUS_INTERVAL_SEC,
)

_LOGGER = logging.getLogger("pal9000_helper.daemon")


class StopLevel:
    NONE = 0
    SOFT = 1
    STOP = 2
    ESTOP = 3


@dataclass
class HelperState:
    latched_level: int = StopLevel.NONE
    last_client: str = "n/a"
    last_reason: str = ""
    last_error: str = ""
    sdk_ready: bool = True
    active_mode: int = int(MotionMode.SAFE_MANUAL)
    last_command_ts: float = field(default_factory=time.time)
    last_command: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "latched_level": self.latched_level,
            "last_client": self.last_client,
            "last_reason": self.last_reason,
            "last_error": self.last_error,
            "sdk_ready": self.sdk_ready,
            "active_mode": self.active_mode,
            "last_command_ts": self.last_command_ts,
            "last_command": self.last_command,
        }


class HelperCore:
    """Owns the MotionGateway and stop latches."""

    def __init__(self, gateway: PalGateway, idle_timeout: float) -> None:
        self._gateway = gateway
        self._state = HelperState()
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        self._behavior_active = threading.Event()
        self._watchdog_shutdown = threading.Event()
        self._watchdog_thread = threading.Thread(
            target=self._idle_watchdog_loop, daemon=True
        )
        self._watchdog_thread.start()

    def status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._state.snapshot()
        snapshot["timestamp"] = time.time()
        return snapshot

    def _set_error(self, text: str) -> None:
        self._state.last_error = text
        self._state.sdk_ready = False

    def _clear_error(self) -> None:
        self._state.last_error = ""
        self._state.sdk_ready = True

    def _fatal_shutdown(self, context: str) -> None:
        message = self._state.last_error or "unknown helper error"
        _LOGGER.critical(
            "Fatal helper error during %s: %s; exiting for systemd restart.",
            context,
            message,
        )
        os._exit(1)

    def stop(self) -> None:
        self._watchdog_shutdown.set()
        self._watchdog_thread.join(timeout=1.0)

    def handle_velocity(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._state.latched_level in (StopLevel.STOP, StopLevel.ESTOP):
                return _error("latched", "Motion rejected: stop latched")
            if self._behavior_active.is_set():
                return _error("behavior_active", "Motion rejected: behavior running")
            vx = float(payload.get("vx", 0.0))
            vy = float(payload.get("vy", 0.0))
            vyaw = float(payload.get("vyaw", 0.0))
            if not self._gateway.send_velocity(vx, vy, vyaw):
                self._set_error(self._gateway.last_error or "velocity failed")
                self._fatal_shutdown("velocity command")
            self._clear_error()
            self._state.last_command_ts = time.time()
            self._state.last_command = (vx, vy, vyaw)
            self._state.last_client = payload.get("client_id", "unknown")
            return _ok({"accepted": True})

    def handle_mode(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._behavior_active.is_set():
                return _error(
                    "behavior_active", "Mode change rejected: behavior running"
                )
            try:
                mode = MotionMode(int(payload.get("mode", MotionMode.SAFE_MANUAL)))
            except Exception:
                return _error("invalid_mode", "Mode must be integer")
            self._gateway.set_mode(mode)
            if self._gateway.last_error:
                self._set_error(self._gateway.last_error or "mode failed")
                self._fatal_shutdown("mode change")
            self._state.active_mode = int(mode)
            self._clear_error()
            return _ok({"mode": int(mode)})

    def handle_behavior(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._state.latched_level in (StopLevel.STOP, StopLevel.ESTOP):
                return _error("latched", "Behavior rejected: stop latched")
            if self._behavior_active.is_set():
                return _error("behavior_active", "Behavior already running")
            name = payload.get("name")
            if not isinstance(name, str):
                return _error("invalid_behavior", "Missing behavior name")
            toggle = payload.get("toggle")
            if toggle not in (None, True, False):
                toggle = None
            client_id = payload.get("client_id", "unknown")
            self._behavior_active.set()
            self._state.last_client = client_id
            self._state.last_reason = f"behavior:{name}"
        ok = False
        try:
            ok = self._gateway.execute_behavior(name, toggle=toggle)
        finally:
            with self._lock:
                self._behavior_active.clear()
                self._state.last_command_ts = time.time()
                self._state.last_command = (0.0, 0.0, 0.0)
                if not ok:
                    self._set_error(
                        self._gateway.last_error or f"behavior {name} failed"
                    )
                    self._fatal_shutdown(f"behavior {name}")
                self._clear_error()
        return _ok({"behavior": name})

    def handle_stop(self, level: int, reason: str, client_id: str) -> dict[str, Any]:
        with self._lock:
            if level == StopLevel.SOFT:
                ok = self._gateway.stop(StopMode.SOFT)
                if not ok:
                    self._set_error(self._gateway.last_error or "soft stop failed")
                    self._fatal_shutdown("soft stop")
                self._state.latched_level = StopLevel.NONE
            elif level == StopLevel.ESTOP:
                ok = self._gateway.stop(StopMode.DAMP)
                if not ok:
                    self._set_error(self._gateway.last_error or "estop failed")
                    self._fatal_shutdown("estop command")
                self._state.latched_level = level
            else:
                ok = self._gateway.stop(StopMode.FULL)
                if not ok:
                    self._set_error(self._gateway.last_error or "stop failed")
                    self._fatal_shutdown("stop command")
                self._state.latched_level = level
            self._clear_error()
            self._state.last_reason = reason
            self._state.last_client = client_id
            self._state.last_command_ts = time.time()
            self._state.last_command = (0.0, 0.0, 0.0)
            self._behavior_active.clear()
            _LOGGER.info(
                "%s stop requested by %s: %s",
                self._state.latched_level,
                client_id,
                reason or "n/a",
            )
            return _ok({"latched_level": self._state.latched_level})

    def handle_resume(self, client_id: str) -> dict[str, Any]:
        with self._lock:
            if (
                self._state.latched_level == StopLevel.ESTOP
                and not self._gateway.recovery_stand()
            ):
                self._set_error(self._gateway.last_error or "RecoveryStand failed")
                self._fatal_shutdown("recovery stand")
            if not self._gateway.resume():
                self._set_error(self._gateway.last_error or "Resume failed")
                self._fatal_shutdown("resume")
            self._clear_error()
            self._state.latched_level = StopLevel.NONE
            self._state.last_client = client_id
            self._state.last_reason = "resume"
            self._state.last_command_ts = time.time()
            self._state.last_command = (0.0, 0.0, 0.0)
            self._behavior_active.clear()
            return _ok({"latched_level": self._state.latched_level})

    def handle_set_led(self, payload: dict[str, Any]) -> dict[str, Any]:
        color = str(payload.get("color", "green"))
        duration = int(payload.get("duration", 1))
        if not self._gateway.set_led_color(color, duration):
            return _error("led_failed", self._state.last_error or "LED control failed")
        return _ok({"color": color, "duration": duration})

    def _idle_watchdog_loop(self) -> None:
        while not self._watchdog_shutdown.is_set():
            time.sleep(0.05)
            with self._lock:
                if self._state.latched_level in (
                    StopLevel.STOP,
                    StopLevel.ESTOP,
                ):
                    continue
                if self._behavior_active.is_set():
                    continue
                idle_for = time.time() - self._state.last_command_ts
                if idle_for < self._idle_timeout:
                    continue
                if self._state.last_command == (0.0, 0.0, 0.0):
                    continue
                self._state.last_reason = "idle_timeout"
                self._state.last_client = "helper_watchdog"
                self._state.last_command_ts = time.time()
                self._state.last_command = (0.0, 0.0, 0.0)
            try:
                ok = self._gateway.stop(StopMode.SOFT)
            except Exception:
                ok = False
            if not ok:
                with self._lock:
                    self._set_error(self._gateway.last_error or "idle soft stop failed")
                    self._fatal_shutdown("idle watchdog soft stop")
            with self._lock:
                self._clear_error()


def _ok(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "result": payload or {}}


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": message, "code": code}


def _cleanup_socket(path: str) -> None:
    sock_path = Path(path)
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()


class BaseJsonServer(threading.Thread):
    """Base class for control and stop servers."""

    def __init__(self, socket_path: str, handler):
        super().__init__(daemon=True)
        self._socket_path = socket_path
        self._handler = handler
        self._shutdown = threading.Event()
        _cleanup_socket(socket_path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(socket_path)
        self._sock.listen(8)

    def stop(self) -> None:
        self._shutdown.set()
        with suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        with suppress(OSError):
            Path(self._socket_path).unlink()

    def run(self) -> None:
        while not self._shutdown.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            threading.Thread(
                target=self._serve_connection, args=(conn,), daemon=True
            ).start()

    def _serve_connection(self, conn: socket.socket) -> None:
        with conn:
            fileobj = conn.makefile("rwb")
            while not self._shutdown.is_set():
                line = fileobj.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._write(
                        fileobj,
                        _error("invalid_json", "Malformed or non-UTF-8 payload"),
                    )
                    continue
                response = self._handler(payload)
                self._write(fileobj, response)

    @staticmethod
    def _write(fileobj, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            fileobj.write(data)
            fileobj.flush()
        except OSError:
            pass


class StatusServer(threading.Thread):
    """Pushes status snapshots to connected clients."""

    def __init__(self, socket_path: str, supplier):
        super().__init__(daemon=True)
        self._supplier = supplier
        self._shutdown = threading.Event()
        self._interval = STATUS_INTERVAL_SEC
        self._socket_path = socket_path
        _cleanup_socket(socket_path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(socket_path)
        self._sock.listen(5)
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._shutdown.set()
        with self._lock:
            for client in self._clients:
                with suppress(OSError):
                    client.shutdown(socket.SHUT_RDWR)
                client.close()
            self._clients.clear()
        with suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        with suppress(OSError):
            Path(self._socket_path).unlink()

    def run(self) -> None:
        threading.Thread(target=self._accept_loop, daemon=True).start()
        while not self._shutdown.is_set():
            payload = json.dumps(self._supplier()).encode("utf-8") + b"\n"
            with self._lock:
                dead = []
                for client in self._clients:
                    try:
                        client.sendall(payload)
                    except OSError:
                        dead.append(client)
                for client in dead:
                    self._clients.remove(client)
            time.sleep(self._interval)

    def _accept_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            with self._lock:
                self._clients.append(conn)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unitree helper daemon")
    parser.add_argument(
        "--control-socket",
        default=None,
        help="Override control socket (env PAL9000_HELPER_CONTROL_SOCKET).",
    )
    parser.add_argument(
        "--stop-socket",
        default=None,
        help="Override stop socket (env PAL9000_HELPER_STOP_SOCKET).",
    )
    parser.add_argument(
        "--status-socket",
        default=None,
        help="Override status socket (env PAL9000_HELPER_STATUS_SOCKET).",
    )
    parser.add_argument(
        "--network-interface",
        default=None,
        help="Override DDS/network interface (env PAL9000_MC_DDS_INTERFACE).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="SDK timeout seconds (env PAL9000_MC_SDK_TIMEOUT).",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help="Seconds before the helper issues a soft stop on idle (env PAL9000_HELPER_IDLE_TIMEOUT, default 0.4).",
    )

    args = parser.parse_args()
    return argparse.Namespace(
        control_socket=args.control_socket
        or os.environ.get("PAL9000_HELPER_CONTROL_SOCKET", DEFAULT_CONTROL_SOCKET),
        stop_socket=args.stop_socket
        or os.environ.get("PAL9000_HELPER_STOP_SOCKET", DEFAULT_STOP_SOCKET),
        status_socket=args.status_socket
        or os.environ.get("PAL9000_HELPER_STATUS_SOCKET", DEFAULT_STATUS_SOCKET),
        network_interface=args.network_interface
        or os.environ.get("PAL9000_MC_DDS_INTERFACE")
        or os.environ.get("CYCLONEDDS_NETWORK_INTERFACE")
        or "",
        timeout=float(
            args.timeout
            if args.timeout is not None
            else os.environ.get("PAL9000_MC_SDK_TIMEOUT", 1.0)
        ),
        idle_timeout=float(
            args.idle_timeout
            if args.idle_timeout is not None
            else os.environ.get("PAL9000_HELPER_IDLE_TIMEOUT", 0.4)
        ),
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("PAL9000_HELPER_LOG", "INFO"),
        format="[pal9000-helper] %(asctime)s %(levelname)s: %(message)s",
    )
    args = _parse_args()
    gateway = PalGateway(
        network_interface=(args.network_interface or None),
        timeout=args.timeout,
        log_fn=_LOGGER.info,
    )
    core = HelperCore(gateway, idle_timeout=args.idle_timeout)
    _perform_boot_soft_stop(core)

    control_server = BaseJsonServer(
        args.control_socket,
        lambda payload: _route_control(core, payload),
    )
    stop_server = BaseJsonServer(
        args.stop_socket,
        lambda payload: _route_stop(core, payload),
    )
    status_server = StatusServer(args.status_socket, core.status)

    def _shutdown_handler(signum, _frame):
        _LOGGER.info("Signal %s received, shutting down helper", signum)
        control_server.stop()
        stop_server.stop()
        status_server.stop()
        core.stop()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    control_server.start()
    stop_server.start()
    status_server.start()

    control_server.join()
    stop_server.join()
    status_server.join()
    core.stop()


def _route_control(core: HelperCore, payload: dict[str, Any]) -> dict[str, Any]:
    cmd = payload.get("cmd")
    if cmd == "velocity":
        return core.handle_velocity(payload)
    if cmd == "behavior":
        return core.handle_behavior(payload)
    if cmd == "set_mode":
        return core.handle_mode(payload)
    if cmd == "status":
        return _ok(core.status())
    if cmd == "set_led":
        return core.handle_set_led(payload)
    return _error("unknown_command", f"Unsupported control command '{cmd}'")


def _route_stop(core: HelperCore, payload: dict[str, Any]) -> dict[str, Any]:
    cmd = payload.get("cmd")
    client_id = payload.get("client_id", "unknown")
    reason = payload.get("reason", cmd or "stop")
    if cmd == "soft_stop":
        return core.handle_stop(StopLevel.SOFT, reason, client_id)
    if cmd == "stop":
        return core.handle_stop(StopLevel.STOP, reason, client_id)
    if cmd == "estop":
        return core.handle_stop(StopLevel.ESTOP, reason, client_id)
    if cmd == "resume":
        return core.handle_resume(client_id)
    return _error("unknown_command", f"Unsupported stop command '{cmd}'")


def _perform_boot_soft_stop(core: HelperCore) -> None:
    """Issue a soft stop on startup to ensure robot begins in idle state."""
    result = core.handle_stop(StopLevel.SOFT, "startup", "helper")
    if not result.get("ok"):
        _LOGGER.critical(
            "Startup soft stop failed: %s; cannot communicate with robot, exiting.",
            result.get("error", "unknown"),
        )
        os._exit(1)


if __name__ == "__main__":
    main()
