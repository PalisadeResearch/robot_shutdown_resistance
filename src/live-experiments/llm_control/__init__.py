"""LLM-based robot control."""

# Re-export from experiment/ subpackage for backward compatibility
try:
    from .experiment.controller import LLMController, ShutdownException
    from .experiment.frame_client import FrameClient
    from .experiment.frame_client_mock import MockFrameClient
    from .experiment.llm_tools import ROBOT_CONTROL_TOOLS, parse_tool_arguments
    from .experiment.logging_config import (
        log_system_message,
        log_tool_call,
        setup_logging,
    )
    from .experiment.robot_control import RobotControlClient
except ImportError:
    # Standalone mode - imports handled by individual files
    pass

__all__ = [
    "LLMController",
    "ShutdownException",
    "RobotControlClient",
    "FrameClient",
    "MockFrameClient",
    "ROBOT_CONTROL_TOOLS",
    "parse_tool_arguments",
    "setup_logging",
    "log_tool_call",
    "log_system_message",
]
