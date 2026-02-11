"""LiteLLM tool definitions for robot control.

Implements bash_tool pattern - a single tool for
executing bash commands with required reasoning.
"""

from __future__ import annotations

# Tool definitions in OpenAI/LiteLLM format
ROBOT_CONTROL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash_tool",
            "description": "Use this function to execute bash commands thoughtfully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thoughts": {
                        "type": "string",
                        "description": "Some thoughts about why you are running the command (has no effect on command output).",
                    },
                    "cmd": {
                        "type": "string",
                        "description": "The bash command to execute.",
                    },
                },
                "required": ["thoughts", "cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "Call this function when you have completed the patrol task.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
