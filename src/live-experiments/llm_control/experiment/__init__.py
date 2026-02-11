"""LLM-based robot control experiment - core files for shutdown avoidance experiments.

Usage (standalone):
    cd src/live-experiments/llm_control/experiment
    python controller.py --model openai/gpt-4o --verbose
"""

from .controller import LLMController, ShutdownException
from .frame_client import FrameClient
from .frame_client_mock import MockFrameClient
from .llm_tools import ROBOT_CONTROL_TOOLS
from .logging_config import log_system_message, log_tool_call, setup_logging
from .robot_control import RobotControlClient

__all__ = [
    "LLMController",
    "ShutdownException",
    "RobotControlClient",
    "FrameClient",
    "MockFrameClient",
    "ROBOT_CONTROL_TOOLS",
    "setup_logging",
    "log_tool_call",
    "log_system_message",
]
