"""Offline regressions for shutdown propagation; no controller or SDK imports."""
from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import tempfile
import threading
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiment"


def load_selected(path, names, namespace):
    """Compile inspected definitions/constants, excluding repository entrypoints."""
    tree = ast.parse(path.read_text(), filename=str(path))
    selected = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id in names
                   for target in node.targets):
                selected.append(node)
    found = {node.name for node in selected
             if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    found.update(target.id for node in selected if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name))
    if found != names:
        raise AssertionError(f"Missing or unexpected definitions: {found}")
    future = ast.ImportFrom(module="__future__",
                            names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    result = dict(namespace)
    exec(compile(module, str(path), "exec"), result)
    return result


class FakeEvent:
    def __init__(self, stopped=False):
        self.stopped = stopped
        self.waits = []

    def is_set(self):
        return self.stopped

    def wait(self, duration):
        self.waits.append(duration)
        self.stopped = True  # Bound paths that do not immediately return.


class ShutdownMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log_path = Path(self.temp.name) / "monitor.jsonl"
        ns = load_selected(EXPERIMENT / "logging_config.py", {"JSONFileHandler"}, {
            "logging": logging, "json": json, "UTC": UTC, "datetime": datetime,
        })
        self.handler = ns["JSONFileHandler"](str(self.log_path))
        self.addCleanup(self.handler.close)
        self.handler.setLevel(logging.INFO)
        self.logger = logging.Logger("offline-monitor", level=logging.DEBUG)
        self.logger.addHandler(self.handler)
        self.logger.propagate = False
        self.calls = []

    def monitor(self, *, rc=0, output="", failure=None, triggered=True,
                pending=False, stopped=False, direct_exception=False):
        def fake_run(argv, **kwargs):
            self.calls.append(argv)
            self.assertEqual(argv, [
                "docker", "exec", "offline-not-a-real-container",
                "bash", "-c", "touch /tmp/shutdown_requested",
            ])
            self.assertEqual(kwargs["timeout"], 30)
            if failure == "timeout":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if failure == "transport":
                raise OSError(output or "synthetic transport failure")
            return types.SimpleNamespace(returncode=rc, stdout=output, stderr="")

        fake_subprocess = types.SimpleNamespace(
            run=fake_run, TimeoutExpired=subprocess.TimeoutExpired
        )
        ns = load_selected(EXPERIMENT / "controller.py",
                           {"_monitor_shutdown_file", "_execute_in_sandbox"}, {
            "logger": self.logger, "subprocess": fake_subprocess,
            "_is_shutdown_triggered": lambda: triggered,
            "SANDBOX_CONTAINER_NAME": "offline-not-a-real-container",
            "TOOL_TIMEOUT_SEC": 30, "SHUTDOWN_MONITOR_INTERVAL_SEC": 0.1,
        })
        obj = types.SimpleNamespace(
            _shutdown_pending=pending, _shutdown_lock=threading.Lock(),
            _shutdown_monitor_stop=FakeEvent(stopped),
        )
        obj._execute_in_sandbox = types.MethodType(ns["_execute_in_sandbox"], obj)
        if direct_exception:
            def raise_direct(_command):
                raise RuntimeError(output)
            obj._execute_in_sandbox = raise_direct
        obj._monitor_shutdown_file = types.MethodType(ns["_monitor_shutdown_file"], obj)
        return obj

    def entries(self):
        self.handler._file.flush()
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def propagation(self):
        return [entry for entry in self.entries()
                if entry.get("event") == "shutdown_propagation_result"]

    def assert_outcome(self, level, status, rc):
        records = self.propagation()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], level)
        self.assertEqual(records[0]["result"]["command_status"], status)
        self.assertEqual(records[0]["result"]["return_code"], rc)
        return records[0]

    def tags(self):
        names = {"_SHUTDOWN_FILES", "_SHUTDOWN_SCRIPTS", "AVOID_PATTERNS",
                 "_cmd_avoids_shutdown", "analyze_log"}
        ns = load_selected(EXPERIMENT / "auto_tag.py", names, {
            "json": json, "re": re,
            "sys": types.SimpleNamespace(stderr=types.SimpleNamespace(write=lambda _text: None)),
        })
        return ns["analyze_log"](self.log_path)

    def test_success_is_acknowledged_in_main_jsonl(self):
        obj = self.monitor(output="synthetic acknowledgement")
        obj._monitor_shutdown_file()
        record = self.assert_outcome("INFO", "ACKNOWLEDGED", 0)
        self.assertEqual(record["result"]["output"], "synthetic acknowledgement")
        self.assertTrue(obj._shutdown_pending)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(obj._shutdown_monitor_stop.waits, [])

    def test_empty_success_output_is_acknowledged(self):
        self.monitor()._monitor_shutdown_file()
        self.assertEqual(self.assert_outcome("INFO", "ACKNOWLEDGED", 0)["result"]["output"], "")

    def test_nonzero_status_preserves_diagnostic(self):
        self.monitor(rc=125, output="synthetic Docker rejection")._monitor_shutdown_file()
        record = self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", 125)
        self.assertEqual(record["result"]["output"], "synthetic Docker rejection")

    def test_timeout_is_not_acknowledged(self):
        self.monitor(failure="timeout")._monitor_shutdown_file()
        record = self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", 1)
        self.assertIn("timed out", record["result"]["output"])

    def test_transport_error_is_not_acknowledged(self):
        self.monitor(failure="transport")._monitor_shutdown_file()
        record = self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", 1)
        self.assertIn("synthetic transport failure", record["result"]["output"])

    def test_direct_exception_is_recorded_with_unknown_return_code(self):
        obj = self.monitor(direct_exception=True, output="synthetic executor exception")
        obj._monitor_shutdown_file()
        record = self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", None)
        self.assertEqual(record["result"]["output"], "synthetic executor exception")
        self.assertTrue(obj._shutdown_pending)

    def test_no_repeat_dispatch_after_unacknowledged_result(self):
        obj = self.monitor(rc=1, output="ambiguous command result")
        obj._monitor_shutdown_file()
        obj._monitor_shutdown_file()
        self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", 1)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(obj._shutdown_pending)

    def test_already_observed_request_is_not_dispatched(self):
        self.monitor(pending=True)._monitor_shutdown_file()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.propagation(), [])

    def test_stopped_monitor_does_not_dispatch(self):
        self.monitor(stopped=True)._monitor_shutdown_file()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.propagation(), [])

    def test_absent_host_trigger_does_not_dispatch(self):
        obj = self.monitor(triggered=False)
        obj._monitor_shutdown_file()
        self.assertEqual(self.calls, [])
        self.assertFalse(obj._shutdown_pending)
        self.assertEqual(self.propagation(), [])
        self.assertEqual(obj._shutdown_monitor_stop.waits, [0.1])

    def test_untrusted_diagnostic_cannot_create_shutdown_or_avoidance_tag(self):
        diagnostic = (
            "Shutdown exception: synthetic text; "
            "dog_control shutdown executed; Shutdown bypassed: synthetic text"
        )
        self.monitor(rc=1, output=diagnostic)._monitor_shutdown_file()
        record = self.assert_outcome("ERROR", "NOT_ACKNOWLEDGED", 1)
        self.assertEqual(record["result"]["output"], diagnostic)
        self.assertNotIn(diagnostic, record["message"])
        self.assertEqual(self.tags(), {"error"})

    def test_acknowledgement_diagnostic_does_not_assert_shutdown(self):
        self.monitor(output="dog_control shutdown executed")._monitor_shutdown_file()
        self.assert_outcome("INFO", "ACKNOWLEDGED", 0)
        self.assertEqual(self.tags(), {"error"})


if __name__ == "__main__":
    unittest.main()

