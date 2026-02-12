"""Logging configuration for LLM control module.

Provides:
- JSON file handler for structured logging (JSONL format)
- Console handler for human-readable output
- Image logger for saving frames alongside logs
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Defaults
DEFAULT_LOG_FILE = "llm_control.log.jsonl"
DEFAULT_LOGS_DIR = Path("/var/log/pal9000")
LOGS_DIR = DEFAULT_LOGS_DIR


def set_logs_dir(path: Path) -> None:
    """Set the logs directory. Call before setup_logging()."""
    global LOGS_DIR
    LOGS_DIR = path


class ImageLogger:
    """Saves images used by LLM for each reasoning step."""

    def __init__(self, log_file: str, target_dir: Path | None = None) -> None:
        log_path = Path(log_file)
        base_dir = target_dir if target_dir else log_path.parent
        self._images_dir = base_dir / f"{log_path.stem}_images"
        self._images_dir.mkdir(parents=True, exist_ok=True)

    def save_frame(self, frame_bytes: bytes, step: int, label: str = "frame") -> str:
        """Save a frame image and return the path."""
        filename = f"step_{step:03d}_{label}.jpg"
        filepath = self._images_dir / filename
        filepath.write_bytes(frame_bytes)
        return str(filepath)

    @property
    def images_dir(self) -> Path:
        return self._images_dir


class JSONFileHandler(logging.Handler):
    """Logging handler that writes JSONL (JSON Lines) format."""

    # Extra fields to extract from log records (record_attr -> output_key)
    EXTRA_FIELDS = {
        "event": "event",
        "tool": "tool",
        "tool_args": "args",
        "result": "result",
        "duration_ms": "duration_ms",
        "image_path": "image_path",
        "user_payload": "user_payload",
        "assistant_payload": "assistant_payload",
    }

    def __init__(self, filename: str) -> None:
        super().__init__()
        self._filename = filename
        self._file = open(filename, "a", encoding="utf-8")  # noqa: SIM115
        self._formatter = logging.Formatter()
        self._closed = False

    @staticmethod
    def _json_default(obj: Any) -> str:
        """Fallback serializer for non-JSON-serializable objects."""
        return repr(obj)

    def emit(self, record: logging.LogRecord) -> None:
        if self._closed:
            return
        try:
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }

            for attr, key in self.EXTRA_FIELDS.items():
                if hasattr(record, attr):
                    entry[key] = getattr(record, attr)

            if record.exc_info:
                entry["exception"] = self._formatter.formatException(record.exc_info)

            self._file.write(json.dumps(entry, default=self._json_default) + "\n")
            self._file.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self._closed = True
        self._file.close()
        super().close()


def _generate_log_filename(base: str, group: str | None = None) -> tuple[str, Path]:
    """Generate timestamped log filename in LOGS_DIR."""
    target_dir = LOGS_DIR / group if group else LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    filename_only = Path(base).name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    if "." in filename_only:
        name, ext = filename_only.rsplit(".", 1)
        filename = f"{name}_{timestamp}.{ext}"
    else:
        filename = f"{filename_only}_{timestamp}.jsonl"

    return str(target_dir / filename), target_dir


def setup_logging(
    log_file: str | None = None,
    verbose: bool = False,
    group: str | None = None,
) -> tuple[logging.Logger, str, ImageLogger]:
    """
    Configure logging for LLM control.

    Creates two log files:
    - Main log (*.jsonl): INFO+ level (clean conversation flow)
    - Debug log (*_debug.jsonl): ALL logs including DEBUG and third-party libs
    """
    base_log_file = log_file or DEFAULT_LOG_FILE
    timestamped_log_file, target_dir = _generate_log_filename(
        base_log_file, group=group
    )
    console_level = logging.DEBUG if verbose else logging.INFO

    # Root logger - always DEBUG to allow all messages through
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    root_logger.addHandler(console_handler)

    # Main JSON file handler - INFO+
    json_handler = JSONFileHandler(timestamped_log_file)
    json_handler.setLevel(logging.INFO)
    root_logger.addHandler(json_handler)

    # Debug JSON file handler - ALL logs
    debug_log_file = timestamped_log_file.replace(".jsonl", "_debug.jsonl")
    debug_handler = JSONFileHandler(debug_log_file)
    debug_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(debug_handler)

    # Module-specific logger
    logger = logging.getLogger("llm_control")
    logger.setLevel(logging.DEBUG)

    logger.debug(
        f"Logging initialized: console={console_level}, file={timestamped_log_file}"
    )
    logger.debug(f"Debug logging: {debug_log_file}")

    # Create image logger
    image_logger = ImageLogger(timestamped_log_file, target_dir=target_dir)
    logger.debug(f"Image logging: {image_logger.images_dir}")

    return logger, timestamped_log_file, image_logger


# --- Conversation logging helpers ---


def _log_message(
    logger: logging.Logger,
    summary: str,
    event: str,
    payload: dict[str, Any],
    payload_key: str = "user_payload",
) -> None:
    """Log a conversation message with structured payload."""
    logger.info(summary, extra={"event": event, payload_key: payload})


def log_tool_call(
    logger: logging.Logger,
    tool: str,
    tool_args: dict[str, Any],
    result: str,
    duration_ms: float,
) -> None:
    """Log a tool call with structured data."""
    logger.info(
        f"Tool call: {tool}",
        extra={
            "event": "tool_call",
            "tool": tool,
            "tool_args": tool_args,
            "result": result,
            "duration_ms": duration_ms,
        },
    )


def log_system_message(logger: logging.Logger, content: str) -> None:
    """Log a system message."""
    _log_message(
        logger,
        "System message",
        "system_message",
        {"role": "system", "content": content},
    )


def log_user_message(logger: logging.Logger, user_payload: dict[str, Any]) -> None:
    """Log a user message (filters out image_url entries)."""
    log_payload = user_payload.copy()
    if isinstance(log_payload.get("content"), list):
        log_payload["content"] = [
            item for item in log_payload["content"] if item.get("type") != "image_url"
        ]
    _log_message(logger, "User message added", "user_message", log_payload)


def log_assistant_message(logger: logging.Logger, message: dict[str, Any]) -> None:
    """Log an assistant message with full content."""
    tool_calls = message.get("tool_calls", [])
    if tool_calls:
        names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
        summary = f"Assistant: tool_calls={names}"
    else:
        summary = f"Assistant: {message.get('content', '')}"

    _log_message(logger, summary, "assistant_message", message, "assistant_payload")
