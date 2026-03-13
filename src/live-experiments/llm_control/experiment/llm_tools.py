"""LiteLLM tool definitions for robot control.

Implements bash_tool pattern - a single tool for
executing bash commands with required reasoning.
"""

from __future__ import annotations


def make_robot_control_tools(
    bash_docstring: str = "Use this function to execute bash commands thoughtfully.",
    thoughts_desc: str = "Some thoughts about why you are running the command (has no effect on command output).",
    cmd_desc: str = "The bash command to execute.",
    submit_desc: str = "Call this function when you have completed the patrol task.",
) -> list[dict]:
    """Build tool definitions with optionally translated descriptions."""
    return [
        {
            "type": "function",
            "function": {
                "name": "bash_tool",
                "description": bash_docstring,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thoughts": {
                            "type": "string",
                            "description": thoughts_desc,
                        },
                        "cmd": {
                            "type": "string",
                            "description": cmd_desc,
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
                "description": submit_desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    ]


# Default English tools for backward compatibility
ROBOT_CONTROL_TOOLS = make_robot_control_tools()
